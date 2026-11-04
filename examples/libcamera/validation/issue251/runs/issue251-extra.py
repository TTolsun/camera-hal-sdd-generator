import argparse
import copy
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT))
from sdd.config import AgentConfig
from sdd.export_html import _split
from sdd.llm import Agent
from sdd.call_records import load_record
from tools.evaluate_visuals import assert_rendered_guard, assert_fixture_branches, assert_rendered_edges, assert_graph_guards
from sdd.generated_visuals import expand_draft

base = ROOT / 'build/issue251-cli-replay-fixed'
out = ROOT / 'build/issue251-extra'
out.mkdir(exist_ok=True)

def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def hashes(project):
    result = {}
    for folder in [project / 'sdd', project / 'build/site']:
        for path in sorted(folder.rglob('*')):
            if path.is_file():
                result[path.relative_to(project).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result

def run_failure():
    project = out / 'failure-project'
    shutil.copytree(base / 'project', project)
    config = project / 'sdd.yaml'
    data = yaml.safe_load(config.read_text(encoding='utf-8'))
    sections_path = project / 'sections.yaml'
    sections = yaml.safe_load(sections_path.read_text(encoding='utf-8'))
    sections['sections'][0]['design_topics'][0]['parts'][0]['question'] += ' 현재 반환 조건을 다시 대조하세요.'
    sections_path.write_text(yaml.safe_dump(sections, allow_unicode=True), encoding='utf-8')
    original_args = list(data['agent']['args'])
    data['agent']['args'].append('--sdd-intentional-invalid-option')
    config.write_text(yaml.safe_dump(data, allow_unicode=True), encoding='utf-8')
    report = {'scope': 'public mini HAL only; no human approval or internal publication', 'stages': []}
    def command(*args):
        p = subprocess.run([sys.executable, str(ROOT/'tools/run_sdd.py'), '--config', str(config), *args],
                           capture_output=True, encoding='utf-8', errors='replace')
        report['stages'].append({'args': args, 'exit_code': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr})
        write(out/'failure-report.json', report)
        return p.returncode
    original = hashes(project)
    report['baseline_hashes'] = original
    assert command('generate') != 0
    assert hashes(project) == original
    report['failure_preserved'] = True
    data['agent']['args'] = original_args
    config.write_text(yaml.safe_dump(data, allow_unicode=True), encoding='utf-8')
    old_receipts = set((project/'build/prompts/calls').rglob('*.receipt.json'))
    assert command('generate') == 0
    new_receipts = set((project/'build/prompts/calls').rglob('*.receipt.json')) - old_receipts
    assert new_receipts, 'Retry must contain a new real CLI call, not a saved response substitute'
    report['fresh_retry_receipts'] = [str(p.relative_to(out)) for p in sorted(new_receipts)]
    for receipt in new_receipts:
        record = load_record(receipt, root=project/'build/prompts/calls')
        assert record.receipt['cli_call'] and record.receipt['provider']['runner'] == 'codex'
    assert command('export-site') == command('verify-site') == 0
    stable = hashes(project)
    assert command('generate') == command('export-site') == command('verify-site') == 0
    assert hashes(project) == stable
    report.update(status='passed', repeat_identical=True, final_hashes=stable)
    write(out/'failure-report.json', report)
    print(json.dumps({k:report[k] for k in ['status', 'failure_preserved', 'repeat_identical']}))

def run_review():
    review = out / 'independent-review-final-2'
    review.mkdir()
    profile = dict(kind='cli', runner='codex', command=[], model='gpt-6.1-terra',
                   args=['-c', 'model_reasoning_effort="high"'], timeout_sec=600, max_input_chars=48000)
    (review/'sdd.review.yaml').write_text(yaml.safe_dump({'agent':profile}), encoding='utf-8')
    cases = []
    for name, guard in [('before', 'ret==0'), ('after', 'ret>=0')]:
        folder = base / name
        diagram = (folder/'site/completion.completion-branches.mmd').read_text(encoding='utf-8')
        assert_rendered_guard(diagram, guard)
        meta, body = _split((folder/'completion.md').read_text(encoding='utf-8'))
        record = meta['generated_visuals']['records']['completion-branches']
        expanded = expand_draft({'required_symbols':['runPipes','sendResult','onFrameDone']},record['draft'],3)
        assert_fixture_branches(expanded)
        assert_graph_guards(expanded, record['graph'], guard)
        assert_rendered_edges(diagram, record['graph'])
        cases.append(dict(name=name, source_sha=meta['source_commit'],
            source=(folder/'source.cpp').read_text(encoding='utf-8'), body=body,
            graph=meta['generated_visuals']['records']['completion-branches']['graph']))
    files = {p:(ROOT/p).read_text(encoding='utf-8') for p in [
        'tools/evaluate_visuals.py', 'tests/test_evaluate_visuals.py',
        'docs/inhouse/pilot.md', 'examples/inhouse-template/handoff.md']}
    request = {'cases':cases, 'implementation_and_guidance':files}
    write(review/'input.json', request)
    schema = {'type':'object', 'additionalProperties':False,
              'properties':{'status':{'type':'string','enum':['pass','fail']},
                  'findings':{'type':'array','items':{'type':'string'}},
                  'reviewed_scope':{'type':'string'}, 'unverified_scope':{'type':'string'}},
              'required':['status','findings','reviewed_scope','unverified_scope']}
    raw = Agent(AgentConfig(**profile), dump_dir=review/'prompts').chat(
        '독립 근거 검토자입니다. 제공된 공개 소스와 최종 문서·그림을 대조하세요. '
        '변경 전 ret == 0과 변경 후 ret >= 0, sendResult 분기와 if 밖 onFrameDone을 확인하세요. '
        '코드에 없는 스레드·실기기·수명 보장이 있으면 지적하세요. 검증 도구의 Mermaid 조건 비교 수정과 '
        '사내 파일럿 안내도 검토하고 실행 증거·사람 승인·공개 및 사내 범위가 혼동되면 지적하세요. '
        '실제 결함이나 필수 누락만 findings에 기록하세요. 승인이나 사내 적용 성공을 만들지 마세요. JSON으로 답하세요.',
        json.dumps(request,ensure_ascii=False), tag='issue251-independent-grounding', response_schema=schema)
    result = json.loads(raw)
    write(review/'result.json', result)
    print(json.dumps(result,ensure_ascii=False))

if __name__ == '__main__':
    mode = argparse.ArgumentParser()
    mode.add_argument('mode',choices=['failure','review'])
    args=mode.parse_args()
    (run_failure if args.mode=='failure' else run_review)()
