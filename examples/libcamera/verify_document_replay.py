"""Independently verify the public remaining-document replay (stdlib only)."""
from pathlib import Path
import argparse
import hashlib
import json
import re


PAGES = {'vendor-assurance', 'vendor-integration', 'pipeline-handler', 'ipa',
         'ipu3-lsc-flow', 'rkisp1-dewarp', 'camera-model', 'request-lifecycle'}


def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def request_sources(user):
    if user.startswith('근거:\n'):
        sources, _ = json.JSONDecoder().raw_decode(user[len('근거:\n'):])
        return sources
    request, _ = json.JSONDecoder().raw_decode(user[user.index('{"reader":'):])
    return request['sources']


def manuscript(path):
    text = path.read_text(encoding='utf-8')
    match = re.fullmatch(r'---\n(.*?)\n---\n(.*)', text, re.S)
    assert match, path
    front, body = match.groups()
    artifact = json.loads(next(line.split(': ', 1)[1] for line in front.splitlines()
                              if line.startswith('generated_design: ')))
    assert sha(body.strip()) == artifact['body_sha256'], path
    return front, artifact


def verify(root, *, complete=True):
    proof = json.loads((root/'proof.json').read_text(encoding='utf-8'))
    stages = proof['stages']
    if complete:
        assert set(stages) == {'baseline', 'mutated', 'restored', 'published'}
        assert all(set(stage['pages']) == PAGES for stage in stages.values())
        source = proof['test_source']
        assert source['official_tree'] == source['restored_tree']
        for stage in ('mutated', 'restored'):
            assert stages[stage]['source_commit'] == source['commits'][stage]
        for stage in ('baseline', 'published'):
            assert stages[stage]['source_commit'] == proof['official_source_commit']
        unchanged = proof['unchanged_source_check']
        assert unchanged['llm_calls_before'] == unchanged['llm_calls_after']
    for key, call in proof['calls'].items():
        receipt = call['receipt']
        assert receipt['transport'] == 'ollama' and receipt['http_call'] is True
        assert receipt['model'] == proof['model']['name'] == 'qwen3.5:9b'
        assert sha(json.dumps(call['request'], ensure_ascii=False, sort_keys=True)) == receipt['request_sha256']
        assert sha(call['response']) == receipt['response_sha256']
        assert key == sha(receipt['request_sha256']+receipt['response_sha256'])
    for stage, record in stages.items():
        for page, entry in record['pages'].items():
            front, artifact = manuscript(root/entry['file'])
            assert record['source_commit'] in front
            assert set(artifact['topic_agents'].values()) == {'ollama/qwen3.5:9b'}
            assert set(entry['origins']) == set(artifact['answers'])
            for topic, answers in artifact['answers'].items():
                origins = entry['origins'][topic]
                assert len(origins) == len(answers)
                for answer, origin in zip(answers, origins):
                    call = proof['calls'][origin['call']]
                    assert call['receipt']['tag'].startswith(f'{page}_{topic}_')
                    raw = json.loads(call['response'])['statements'][origin['index']]
                    assert answer['text'].replace('`', '') == raw['text'].replace('`', '')
                    assert answer['covers'] == raw['covers'] and answer['kind'] == raw['kind']
                    user = call['request']['user']
                    sources = request_sources(user)
                    passage = next((sid, p['text'].strip()) for sid, parts in sources.items()
                                   for p in parts if p.get('quote_id') == raw['quote_id'])
                    assert answer['evidence'] == [passage[0]] and answer['quote'] == passage[1]
            for expectation in entry.get('expectations', []):
                text = ' '.join(a['text'] for a in artifact['answers'][expectation['topic']])
                for pattern in expectation.get('require', []):
                    assert re.search(pattern, text), (stage, page, pattern, text)
                for pattern in expectation.get('reject', []):
                    assert not re.search(pattern, text), (stage, page, pattern, text)
            if stage in ('mutated', 'restored'):
                assert artifact['generated_topics'], (stage, page, 'No actual regenerated topic')
                assert page in record['impact']['sections']
                previous = stages['baseline' if stage == 'mutated' else 'mutated']['pages'][page]
                _, prior = manuscript(root/previous['file'])
                for topic in artifact['reused_topics']:
                    assert artifact['answers'][topic] == prior['answers'][topic]
                assert any(artifact['answers'][topic] != prior['answers'][topic]
                           for topic in artifact['generated_topics']), (stage, page, 'Unchanged answer')
            if stage == 'published':
                _, restored = manuscript(root/stages['restored']['pages'][page]['file'])
                assert artifact['answers'] == restored['answers']
                deployed = root.parent/'docs'/f'{page}.md'
                if deployed.exists():
                    assert deployed.read_bytes() == (root/entry['file']).read_bytes()
        for entry in record.get('structural', {}).values():
            text = (root/entry['file']).read_text(encoding='utf-8')
            assert sha(text) == entry['sha256']
            assert record['source_commit'] in text
            for value in entry.get('required', []):
                assert value in text
            for value in entry.get('rejected', []):
                assert value not in text
        if stage in ('mutated', 'restored'):
            assert record['update_state']['last_done'] == record['source_commit']
            assert not record['update_state']['failed']
            assert record['facts']['translation_units'] == 300
            assert record['facts']['parse_errors'] == 0
    if complete:
        assert stages['mutated']['structural'], 'Missing deterministic document checks'
        assert set(stages['mutated']['structural']) == set(stages['restored']['structural'])
        scenario = 'scenarios/queue_request.md'
        def count(stage):
            entry = stages[stage]['structural'][scenario]
            return (root/entry['file']).read_text(encoding='utf-8').count('sequence')
        assert count('mutated') > count('baseline'), 'New source call missing from scenario'
        assert count('restored') == count('baseline'), 'Removed source call remains in scenario'
    print(f"Verified {len(proof['calls'])} actual Ollama responses across {len(stages)} stages.")
    print('Controlled source replay; this is neither an upstream change nor human approval.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    verify(parser.parse_args().root)
