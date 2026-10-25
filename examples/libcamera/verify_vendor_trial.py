"""Verify saved Vendor manuscripts against actual model HTTP receipts.

This verifies provenance and coverage, not the truth of natural-language claims.
No third-party packages or model connection are needed to inspect a trial.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def verify(root):
    root = Path(root)
    report = json.loads((root / 'evaluation.json').read_text(encoding='utf-8'))
    assert hashlib.sha256((root / 'sections.yaml').read_bytes()).hexdigest() == report['sections_sha256']
    assert report['publishable'] is False and report['human_approval'] == 'pending'
    calls = []
    for path in sorted((root / 'calls').rglob('*.receipt.json')):
        prefix = str(path).removesuffix('.receipt.json')
        receipt = json.loads(path.read_text(encoding='utf-8'))
        request = json.loads(Path(prefix + '.request.json').read_text(encoding='utf-8'))
        response = Path(prefix + '.response.txt').read_text(encoding='utf-8')
        assert receipt['http_call'] is True and receipt['transport'] == report['provider']
        assert receipt['model'] == report['model']
        assert receipt['request_sha256'] == digest(json.dumps(request, ensure_ascii=False, sort_keys=True))
        assert receipt['response_sha256'] == digest(response)
        assert all(receipt['settings'][k] == report['settings'][k]
                   for k in ('temperature', 'think', 'num_ctx', 'max_output_tokens'))
        calls.append((receipt, request, response))
    assert calls, 'Missing actual HTTP receipts'
    repairing = report.get('execution_mode') == 'verified-http-replay-and-live-repair'
    origins = {(r['request_sha256'], r['response_sha256']) for r, _, _ in calls}
    replayed = set()
    if repairing:
        for path in sorted((root / 'replay-prompts/calls').rglob('*.receipt.json')):
            prefix = str(path).removesuffix('.receipt.json')
            receipt = json.loads(path.read_text(encoding='utf-8'))
            request = json.loads(Path(prefix + '.request.json').read_text(encoding='utf-8'))
            response = Path(prefix + '.response.txt').read_text(encoding='utf-8')
            pair = (digest(json.dumps(request, ensure_ascii=False, sort_keys=True)), digest(response))
            assert pair == (receipt['request_sha256'], receipt['response_sha256']) and pair in origins
            assert receipt['transport'] == 'response-bundle' and receipt['http_call'] is False
            assert receipt['model'] == report['model']
            replayed.add(pair)
        assert replayed, 'Repair manuscripts require replay receipts bound to actual HTTP origins'
    count, visual_count = 0, 0
    for result in report['results']:
        assert result['automatic_checks'] == 'passed', result
        for item in result['manuscripts']:
            path = root / item['path']
            assert hashlib.sha256(path.read_bytes()).hexdigest() == item['sha256']
            match = re.fullmatch(r'---\n(.*?)\n---\n(.*)', path.read_text(encoding='utf-8'), re.S)
            assert match, path
            front, body = match.groups()
            assert f"source_commit: {report['source_commit']}" in front
            artifact = json.loads(next(line.split(': ', 1)[1] for line in front.splitlines()
                                       if line.startswith('generated_design: ')))
            assert artifact['body_sha256'] == digest(body.strip())
            transport = 'response-bundle' if repairing else report['provider']
            assert set(artifact['topic_agents'].values()) == {transport + '/' + report['model']}
            for topic, answers in artifact['answers'].items():
                for answer in answers:
                    tag = f"{result['section']}_{topic}_{answer['part_id']}_"
                    matched = False
                    for receipt, request, response in calls:
                        if not receipt['tag'].startswith(tag):
                            continue
                        if repairing and (receipt['request_sha256'], receipt['response_sha256']) not in replayed:
                            continue
                        try:
                            raw_answers = json.loads(response)['statements']
                            user = request['user']
                            payload, _ = json.JSONDecoder().raw_decode(user[user.index('{"reader":'):])
                        except (ValueError, KeyError):
                            continue  # Invalid attempts remain in the receipt archive.
                        for raw in raw_answers:
                            if raw['text'].replace('`', '') != answer['text'].replace('`', ''):
                                continue
                            for sid, passages in payload['sources'].items():
                                for passage in passages:
                                    if passage.get('quote_id') == raw.get('quote_id'):
                                        matched |= (answer['evidence'] == [sid]
                                                    and answer['quote'] == passage['text'].strip()
                                                    and answer['covers'] == raw['covers']
                                                    and answer['kind'] == raw['kind'])
                    assert matched, (result['section'], topic, answer['part_id'])
                    count += 1
            visual_lines = [line.split(': ', 1)[1] for line in front.splitlines()
                            if line.startswith('generated_visuals: ')]
            if visual_lines:
                visual = json.loads(visual_lines[0])
                assert visual['body_sha256'] == digest(body.strip())
                for ident, record in visual['records'].items():
                    assert record['producer'] == transport + '/' + report['model']
                    matching = []
                    for receipt, _, response in calls:
                        if not receipt['tag'].startswith(f"visual_{result['section']}_{ident}_"):
                            continue
                        if repairing and (receipt['request_sha256'], receipt['response_sha256']) not in replayed:
                            continue
                        try:
                            matching.append(json.loads(response) == record['draft'])
                        except ValueError:
                            continue
                    assert any(matching), (result['section'], ident, 'visual HTTP origin')
                    visual_count += 1
    return {'answers': count, 'visuals': visual_count, 'http_calls': len(calls), 'replayed_requests': len(replayed),
            'execution_mode': report.get('execution_mode', 'fresh-http-trial'), 'source_commit': report['source_commit'],
            'semantic_approval': False, 'human_approval': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    print(json.dumps(verify(parser.parse_args().root), indent=2))
