"""Verify recorded local-Qwen overview provenance (Python standard library only)."""
from pathlib import Path
import argparse
import hashlib
import json
import re


def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def manuscript(path):
    match = re.fullmatch(r'---\n(.*?)\n---\n(.*)', path.read_text(encoding='utf-8'), re.S)
    assert match, f'Missing manuscript metadata: {path}'
    front, body = match.groups()
    artifact = json.loads(next(x.split(': ', 1)[1] for x in front.splitlines()
                              if x.startswith('generated_design: ')))
    assert sha(body.strip()) == artifact['body_sha256'], path
    return front, artifact


def verify(root, *, complete=True):
    proof = json.loads((root / 'proof.json').read_text(encoding='utf-8'))
    if complete:
        assert set(proof['stages']) == {'baseline', 'mutated', 'restored', 'published'}
        assert all(set(stage['pages']) == {'vendor-overview', 'overview'} for stage in proof['stages'].values())
        source = proof['test_source']
        assert source['official_tree'] == source['restored_tree']
        for stage in ('mutated', 'restored'):
            assert proof['stages'][stage]['source_commit'] == source['commits'][stage]
        assert proof['stages']['baseline']['source_commit'] == proof['official_source_commit']
        unchanged = proof['unchanged_source_check']
        assert unchanged['llm_calls_before'] == unchanged['llm_calls_after']
    calls = proof['calls']
    for key, call in calls.items():
        receipt = call['receipt']
        assert receipt['transport'] == 'ollama' and receipt['http_call'] is True
        assert receipt['model'] == proof['model']['name'] == 'qwen3.5:9b'
        assert sha(json.dumps(call['request'], ensure_ascii=False, sort_keys=True)) == receipt['request_sha256']
        assert sha(call['response']) == receipt['response_sha256']
        assert key == sha(receipt['request_sha256'] + receipt['response_sha256'])
    for stage, record in proof['stages'].items():
        for page, entry in record['pages'].items():
            front, artifact = manuscript(root / entry['file'])
            assert record['source_commit'] in front
            assert set(artifact['topic_agents'].values()) == {'ollama/qwen3.5:9b'}
            assert set(entry['origins']) == set(artifact['answers'])
            for topic, answers in artifact['answers'].items():
                origins = entry['origins'][topic]
                assert len(origins) == len(answers)
                for answer, origin in zip(answers, origins):
                    call = calls[origin['call']]
                    assert call['receipt']['tag'].startswith(f'{page}_{topic}_')
                    raw = json.loads(call['response'])['statements'][origin['index']]
                    assert answer['text'].replace('`', '') == raw['text'].replace('`', '')
                    assert answer['covers'] == raw['covers'] and answer['kind'] == raw['kind']
                    user = call['request']['user']
                    request, _ = json.JSONDecoder().raw_decode(user[user.index('{"reader":'):])
                    passage = next((sid, p['text'].strip()) for sid, parts in request['sources'].items()
                                   for p in parts if p.get('quote_id') == raw['quote_id'])
                    assert answer['evidence'] == [passage[0]] and answer['quote'] == passage[1]
            expected = record['queue_limit']
            text = ' '.join(a['text'] for a in artifact['answers']['queue-limit'])
            assert re.search(rf'(?<!\d){expected}(?!\d)', text), (stage, page, text)
            other = 16 if expected == 32 else 32
            assert not re.search(rf'(?<!\d){other}(?!\d)', text), (stage, page, text)
            if stage in ('mutated', 'restored'):
                assert artifact['generated_topics'] == ['queue-limit']
                previous = proof['stages']['baseline' if stage == 'mutated' else 'mutated']['pages'][page]
                _, previous_artifact = manuscript(root / previous['file'])
                for topic in artifact['reused_topics']:
                    assert artifact['answers'][topic] == previous_artifact['answers'][topic]
        if stage in ('mutated', 'restored'):
            assert record['update_state']['last_done'] == record['source_commit']
            assert record['update_state']['failed'] == {}
            assert {'vendor-overview', 'overview'} <= set(record['impact']['sections'])
            assert record['facts']['translation_units'] == 300
            assert record['facts']['parse_errors'] == 0
    if 'published' in proof['stages']:
        assert proof['stages']['published']['source_commit'] == proof['official_source_commit']
        for page, entry in proof['stages']['published']['pages'].items():
            _, published = manuscript(root / entry['file'])
            _, restored = manuscript(root / proof['stages']['restored']['pages'][page]['file'])
            assert published['answers'] == restored['answers']
            deployed = root.parent / 'docs' / f'{page}.md'
            if deployed.is_file():
                assert deployed.read_text(encoding='utf-8') == (root / entry['file']).read_text(encoding='utf-8')
    print(f'Verified {len(calls)} actual Ollama response records across {len(proof["stages"])} stages.')
    print('This is a controlled 32 -> 16 -> 32 source mutation test, not an upstream change or human approval.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path, nargs='?', default=Path(__file__).resolve().parent)
    verify(parser.parse_args().root)
