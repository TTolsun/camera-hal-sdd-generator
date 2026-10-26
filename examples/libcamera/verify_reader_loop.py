"""Audit a completed reader loop's HTTP provenance, not semantic correctness."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json

import yaml

from sdd import reader_loop_policy as policy
from sdd.reader_loop import latest_response


def verify(root):
    root = Path(root)
    report = json.loads((root/'loop.json').read_text(encoding='utf-8'))
    assert report['stop_reason'] == 'model_review_complete'
    assert report['publishable'] is False and report['human_approval'] == 'pending'
    assert len(report['rounds']) <= report['limits']['max_rounds']
    assert report['http_attempts'] <= report['limits']['max_calls']
    actual, previously_reviewed = set(), {}
    previous = None
    for entry in report['rounds']:
        directory = root/f"round-{entry['round']:02d}"
        raw_sections = (directory/'sections.yaml').read_bytes()
        sections = yaml.safe_load(raw_sections)['sections']
        assert policy.digest(sections) == entry['sections_sha256']
        if previous is not None:
            assert previous == raw_sections, 'Next round differs from the saved proposal'
        previous = ((directory/'proposed-sections.yaml').read_bytes()
                    if (directory/'proposed-sections.yaml').exists() else None)
        model_responses = {}
        for folder in (directory/'diagnosis-prompts/calls', directory/'trial/new-prompts/calls',
                       directory/'trial/prompts/calls'):
            for path in folder.rglob('*.receipt.json'):
                prefix = str(path).removesuffix('.receipt.json')
                receipt = json.loads(path.read_text(encoding='utf-8'))
                request = json.loads(Path(prefix+'.request.json').read_text(encoding='utf-8'))
                raw = Path(prefix+'.response.txt').read_text(encoding='utf-8')
                assert receipt['http_call'] is True and receipt['model'] == report['model']
                assert receipt['transport'] == report['provider']
                assert receipt['request_sha256'] == policy.digest(request)
                assert receipt['response_sha256'] == hashlib.sha256(raw.encode()).hexdigest()
                actual.add(path.relative_to(root).as_posix())
                if folder == directory/'diagnosis-prompts/calls':
                    payload, _ = json.JSONDecoder().raw_decode(request['user'])
                    model_responses[receipt['tag']] = (raw, payload)
        for review in entry['reviews']:
            if review.get('status') == 'not_reached':
                continue
            target = review['target'].replace('/', '_')
            receipt, answer = latest_response(directory/'trial', review['target'])
            assert receipt['request_sha256'] == review['request_sha256']
            assert receipt['response_sha256'] == review['response_sha256']
            assert receipt.get('origins') == review.get('assembly_origins')
            if review['reused_review']:
                assert previously_reviewed[review['review_key']] == review['diagnosis']
            else:
                tag='diagnose_'+target
                if 'diagnosis_attempts' in review:tag+='_'+str(review['diagnosis_attempts']-1)
                raw, payload = model_responses[tag]
                assert all(k.endswith(':current') for k in payload['candidates'])
                assert policy.decode(raw, payload['candidates'], diagnosis=True) == review['diagnosis']
                previously_reviewed[review['review_key']] = review['diagnosis']
            if review.get('plan_attempts'):
                raw, payload = model_responses[f"plan_{target}_{review['plan_attempts']-1}"]
                assert policy.decode(raw, payload['candidates']) == review['proposal']
                assert set(payload['required_expansions']) <= set(review['proposal']['expand'])
                if payload.get('split_required'):
                    assert 2 <= len(review['proposal']['subquestions']) <= 4
            else:
                assert review['diagnosis'] == review['proposal']
    assert len(actual) <= report['http_attempts']  # Failed HTTP attempts may have no receipt.
    final_reviews = report['rounds'][-1]['reviews']
    assert {r['target'] for r in final_reviews} == set(report['targets'])
    assert all(r['proposal']['verdict'] == 'acceptable' and not r['automatic_error'] for r in final_reviews)
    spec = importlib.util.spec_from_file_location('vendor_trial_proof', Path(__file__).with_name('verify_vendor_trial.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    manuscript = module.verify(root/report['candidate_trial'])
    return dict(rounds=len(report['rounds']), new_http_receipts=len(actual), http_attempts=report['http_attempts'],
        diagnosed_targets=len(report['targets']), excluded_units=len(report['excluded_units']),
        manuscript=manuscript, semantic_approval=False, human_approval=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    print(json.dumps(verify(parser.parse_args().root), indent=2))
