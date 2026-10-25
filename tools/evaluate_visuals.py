"""Real local-model replay on the public mini HAL, also runnable from an import ZIP.

No authored graph or response bundle is supplied. This records draft/source
bindings, not independent semantic approval or camera runtime validation.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def main():
    import yaml
    from sdd.config import load
    from sdd.evidence import collect
    from sdd.facts.model import KnowledgeModel
    from sdd.export_html import _split
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True, help='New public-fixture output directory')
    parser.add_argument('--model', default='qwen3.5:9b')
    parser.add_argument('--base-url', default='http://localhost:11434')
    args = parser.parse_args()
    if args.out.exists():
        raise ValueError('Use a new output directory; previous evidence is preserved')
    out = args.out.resolve()
    out.mkdir(parents=True)
    report = {'schema': 1, 'model': args.model, 'scope': 'Public mini HAL source/excerpt replay; no camera execution or internal HAL validation',
              'human_review': 'pending', 'stages': []}
    def write_report():
        (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    def git(*arguments):
        return subprocess.check_output(['git', '-C', str(source), *arguments], text=True).strip()
    def command(*arguments, expect_failure=False):
        proc = subprocess.run([sys.executable, str(ROOT / 'tools/run_sdd.py'), '--config', str(config), *arguments],
                              capture_output=True, encoding='utf-8', errors='replace', env={**__import__('os').environ, 'PYTHONIOENCODING': 'utf-8'})
        report['stages'].append({'command': list(arguments), 'exit_code': proc.returncode,
                                 'stdout': proc.stdout[-3000:], 'stderr': proc.stderr[-3000:]})
        write_report()
        if expect_failure:
            assert proc.returncode != 0, 'Stale source must not publish'
        elif proc.returncode:
            raise RuntimeError(f'{arguments}: {proc.stderr[-1600:]}')
    source = out / 'source'
    source.mkdir()
    file = source / 'src/device/RequestManager.cpp'
    file.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / 'examples/mini-hal/src/device/RequestManager.cpp', file)
    git('init', '-q')
    def commit(message):
        git('add', '.')
        git('-c', 'user.name=SDD public fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', message)
        return git('rev-parse', 'HEAD')
    before = commit('Public mini HAL source before guard change')
    project = out / 'project'
    project.mkdir()
    section = {'id': 'completion-demo', 'title': '공개 mini HAL의 완료 분기', 'output': 'completion.md',
               'kind': 'prose', 'show_evidence': True, 'design_generation': 'llm', 'diagram': {'enabled': False},
               'lead': '파이프 반환 조건과 완료 정리를 소스와 함께 확인하세요.', 'watch': ['src/device/RequestManager.cpp'],
               'design_requirements': [{'id': 'completion', 'question': 'runPipes의 결과별 sendResult와 onFrameDone 호출은 어떻게 다릅니까?'}],
               'design_topics': [{'id': 'completion', 'title': '결과 전송과 프레임 정리',
                                 'question': 'RequestManager::onFrame에서 runPipes 반환값에 따른 sendResult 조건과 onFrameDone 호출을 설명하세요. if 블록 안팎을 구분하고 실패 시 정리도 설명하세요. 실행 스레드나 성공 보장을 추정하지 마세요.',
                                 'answer_contract': {'basis': 'implementation',
                                     'required_terms': [['runPipes'], ['sendResult'], ['onFrameDone'], ['항상', '조건과 무관', '성공 여부와 관계없이', '실패 시에도', '실패하더라도']],
                                     'reject_patterns': [{'pattern': 'onFrameDone[^.!?]*(?:성공[^.!?]*때만|성공한 경우에만)',
                                                          'message': 'onFrameDone은 if 블록 밖입니다. 성공 때만 호출된다고 쓰면 안 됩니다.'}]},
                                 'covers': ['completion'], 'sources': [{'id': 'on-frame', 'file': 'src/device/RequestManager.cpp',
                                     'start': 'void RequestManager::onFrame(Frame &frame)', 'end': '\nvoid RequestManager::sendResult'}]}],
               'next': {'title': '완료 분기', 'link': 'completion.md'}}
    (project / 'sections.yaml').write_text(yaml.safe_dump({'sections': [section]}, allow_unicode=True), encoding='utf-8')
    # Isolate the requested graph subsystem. Natural-language Qwen answers are
    # evaluated elsewhere; source questions do not claim behavioral coverage.
    section.pop('design_generation')
    section.pop('design_requirements')
    section['narration'] = 'facts'
    topic = section['design_topics'][0]
    topic.pop('answer_contract')
    topic.pop('covers')
    topic['narration'] = 'facts'
    report['prose_mode'] = 'source-question view; no generated behavioral answer and no prose substitute'
    (project / 'sections.yaml').write_text(yaml.safe_dump({'sections': [section]}, allow_unicode=True), encoding='utf-8')
    shutil.copyfile(ROOT / 'examples/mini-hal/config/visual-questions.yaml', project / 'visuals.yaml')
    data = {'source': {'root': str(source), 'compile_commands': 'unused.json'},
            'paths': {'sections_file': 'sections.yaml', 'prompts': str(ROOT / 'prompts'), 'templates': str(ROOT / 'templates'), 'style': str(ROOT / 'style')},
            'output': {'facts_dir': 'facts', 'sdd_dir': 'sdd'}, 'visuals': {'file': 'visuals.yaml', 'max_nodes': 3},
            'agent': {'kind': 'ollama', 'model': args.model, 'base_url': args.base_url, 'max_input_chars': 30000,
                      'num_ctx': 16384, 'max_output_tokens': 6000, 'think': False, 'timeout_sec': 600},
            'review': {'require_citations': True, 'max_retries': 1}, 'site': {'enabled': False, 'title': '공개 모델 재생성 시험'}}
    config = project / 'sdd.yaml'
    config.write_text(yaml.safe_dump(data, allow_unicode=True), encoding='utf-8')
    cfg = load(config)
    def facts(sha):
        model = KnowledgeModel(meta={'source_commit': sha, 'build_config': 'public-excerpt-fixture'})
        collect(cfg, model)
        assert all(r['status'] == 'available' for r in model.evidence.values())
        model.save(cfg.facts_path)
    def snapshot(name, guard):
        manuscript = cfg.sdd_dir / 'completion.md'
        meta, body = _split(manuscript.read_text(encoding='utf-8'))
        rec = meta['generated_visuals']['records']['completion-branches']
        assert any(guard in ''.join(e['label'].split()) for e in rec['graph']['edges']), rec['graph']
        assert len(rec['graph']['nodes']) >= 2 and len(rec['graph']['edges']) >= 1
        site = cfg.build_dir / 'site'
        assert guard in ''.join(html.unescape((site / 'completion.completion-branches.mmd').read_text(encoding='utf-8')).split())
        dest = out / name
        shutil.copytree(site, dest / 'site')
        shutil.copyfile(manuscript, dest / 'completion.md')
        original = subprocess.check_output(['git', '-C', str(source), 'show', meta['source_commit'] + ':src/device/RequestManager.cpp'])
        (dest / 'source.cpp').write_bytes(original)
        return {'source_commit': meta['source_commit'], 'input_fingerprint': rec['input_fingerprint'],
                'source_sha256': hashlib.sha256(original).hexdigest(),
                'draft': rec['draft'], 'graph': rec['graph'], 'producer': rec['producer'], 'reused': rec['reused']}
    try:
        with urllib.request.urlopen(args.base_url + '/api/tags', timeout=15) as response:
            report['runtime'] = json.load(response)
        facts(before)
        command('generate')
        command('export-site'); command('verify-site')
        report['before'] = snapshot('before', 'ret==0')
        stable = (cfg.build_dir / 'site/site-manifest.json').read_bytes()
        command('export-site')
        assert (cfg.build_dir / 'site/site-manifest.json').read_bytes() == stable
        file.write_text(file.read_text(encoding='utf-8').replace('if (ret == 0)', 'if (ret >= 0)'), encoding='utf-8')
        after = commit('Change public mini HAL result guard to nonnegative')
        facts(after)
        command('export-site', expect_failure=True)
        assert (cfg.build_dir / 'site/site-manifest.json').read_bytes() == stable
        command('impact', '--base', before, '--head', after)
        command('generate', '--from-impact')
        command('export-site'); command('verify-site')
        report['after'] = snapshot('after', 'ret>=0')
        assert report['before']['input_fingerprint'] != report['after']['input_fingerprint']
        assert not report['after']['reused']
        receipts, graph_drafts = [], []
        for path in sorted((cfg.build_dir / 'prompts/calls').rglob('*.receipt.json')):
            receipt = json.loads(path.read_text(encoding='utf-8'))
            assert receipt['http_call'] and receipt['transport'] == 'ollama'
            request = path.with_name(path.name.replace('.receipt.json', '.request.json'))
            response = path.with_name(path.name.replace('.receipt.json', '.response.txt'))
            assert hashlib.sha256(response.read_bytes()).hexdigest() == receipt['response_sha256']
            assert request.exists()
            payload = json.loads(request.read_text(encoding='utf-8'))
            assert hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True).encode()).hexdigest() == receipt['request_sha256']
            if receipt['tag'].startswith('visual_'):
                graph_drafts.append(json.loads(response.read_text(encoding='utf-8')))
            receipts.append(receipt)
        graph_calls = [r for r in receipts if r['tag'].startswith('visual_')]
        assert len(graph_calls) >= 2
        assert report['before']['draft'] in graph_drafts and report['after']['draft'] in graph_drafts
        report.update(status='passed', graph_http_calls=len(graph_calls), total_http_calls=len(receipts),
                      repeat_build_identical=True, stale_export_preserved=True, receipts=receipts)
    except Exception as exc:
        report.update(status='failed', error=str(exc))
        raise
    finally:
        write_report()
    print(json.dumps({k: report[k] for k in ('status', 'graph_http_calls', 'total_http_calls')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
