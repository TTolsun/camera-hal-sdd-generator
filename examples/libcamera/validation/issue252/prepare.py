"""Freeze the bounded public experiment before any native generation call."""
from pathlib import Path
from copy import deepcopy
import gzip
import hashlib
import json
import shutil
import subprocess
import yaml

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
WORK = ROOT / 'build/issue252'
PUBLIC = WORK / 'public'
BASE = PUBLIC / 'publication/issue214'
RUN = WORK / 'run'
SOURCE = WORK / 'source'
COMMIT = '293d751a814e0d4c34e85ad457ccd9d5eefd1a61'
HEAD = 'be7e83e91348250c015aad6d6f59f1468555bae8'


class NoAliases(yaml.SafeDumper):
    def ignore_aliases(self,data):
        return True


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def main():
    provenance_bytes = (WORK/'build-provenance-fresh.json').read_bytes()
    provenance = json.loads(provenance_bytes)
    assert provenance['status']=='passed' and provenance['source_commit']==COMMIT
    assert provenance['source_clean_before_and_after'] and provenance['exit_code']==0
    assert provenance['full_rebuild'] and provenance['fresh_configuration'] and provenance['setup_exit_code']==0
    assert provenance['required_options']==dict(pipelines=['uvcvideo'],ipas=[],gstreamer='disabled',test=False,
                                              cam='enabled',qcam='disabled',documentation='disabled',**{'lc-compliance':'disabled'})
    for binding in provenance['inputs'].values():
        assert hashlib.sha256((WORK/binding['file']).read_bytes()).hexdigest()==binding['sha256']
    for rel,sha in provenance['generated_inputs'].items():
        assert hashlib.sha256((WORK/'build-inputs-fresh/generated'/rel).read_bytes()).hexdigest()==sha
    if RUN.exists():
        raise ValueError('Preserve the frozen run; use a new run for another preparation.')
    RUN.mkdir(parents=True)
    git = lambda *args: subprocess.check_output(['git', '-C', str(SOURCE), *args])
    assert git('rev-parse', 'HEAD').decode().strip() == COMMIT
    assert not git('status','--porcelain=v1','--untracked-files=all'), 'Generation checkout must be clean.'
    assert not any(line[:1].islower() or line[:1]=='S' for line in git('ls-files','-v').decode().splitlines()), 'Suppressed Git change detection is not allowed in this public fixture.'
    topics = yaml.safe_load((HERE/'topics.yaml').read_bytes())['topics']
    # Add source questions to the real example; do not replace old contracts.
    section_path = ROOT/'examples/libcamera/config/sections.yaml'
    text = section_path.read_text(encoding='utf-8')
    left, right = text.index('- id: request-lifecycle\n'), text.index('- id: request-diagnosis\n')
    selected = text[left:right]
    if 'id: preparation-depth' not in selected:
        rendered = yaml.safe_dump(topics, allow_unicode=True, sort_keys=False, width=105)
        selected = selected.replace('  design_requirements:\n',
                                    ''.join(('  '+line).rstrip()+'\n' for line in rendered.splitlines())+'  design_requirements:\n')
        requirements = [dict(id=t['id'], question=t['question']) for t in topics]
        rendered = yaml.safe_dump(requirements, allow_unicode=True, sort_keys=False, width=105)
        selected = selected.replace('  reader_profile: vendor\n',
                                    ''.join(('  '+line).rstrip()+'\n' for line in rendered.splitlines())+'  reader_profile: vendor\n')
        section_path.write_text(text[:left]+selected+text[right:], encoding='utf-8', newline='\n')
    current = yaml.safe_load(section_path.read_bytes())
    target = next(s for s in current['sections'] if s['id']=='request-lifecycle')
    shutil.copytree(BASE/'config', RUN/'config')
    baseline_sections = yaml.safe_load((BASE/'config/sections.yaml').read_bytes())
    baseline_sections['sections'] = [deepcopy(target) if s['id']=='request-lifecycle' else s
                                     for s in baseline_sections['sections']]
    (RUN/'config/sections.yaml').write_text(yaml.safe_dump(baseline_sections,allow_unicode=True,sort_keys=False),encoding='utf-8')
    glossary_path = RUN/'config/glossary.yaml'
    glossary = yaml.safe_load(glossary_path.read_bytes())
    current_glossary = yaml.safe_load((ROOT/'examples/libcamera/config/glossary.yaml').read_bytes())
    known = {term['term'] for term in glossary['terms']}
    glossary['terms'].extend(deepcopy(term) for term in current_glossary['terms']
                            if term['term'] in {'QBUF','STREAMOFF','DQBUF'} and term['term'] not in known)
    aliases = next(term for term in glossary['terms'] if term['term']=='errno')['aliases']
    if 'ENOENT' not in aliases:
        aliases.append('ENOENT')
    glossary_path.write_text(yaml.safe_dump(glossary,allow_unicode=True,sort_keys=False),encoding='utf-8')
    # Question-specific figures use the existing source-bound generator.
    visuals = yaml.safe_load((BASE/'config/visuals.yaml').read_bytes())
    current_visuals = yaml.safe_load((ROOT/'examples/libcamera/config/visuals.yaml').read_bytes())
    visuals['sections']['request-lifecycle'] = current_visuals['sections']['request-lifecycle']
    questions = {
        'preparation-depth': 'fence 신호 또는 타임아웃에서 prepared_가 설정된 뒤 선두 준비·큐 한도를 검사하고, 재진입 전 pop하여 전달하는 흐름은 무엇입니까?',
        'uvc-depth': 'UVC 제출 실패의 취소와 장치 버퍼 알림의 명시적 요청 완료는 어떻게 구분됩니까?',
        'stop-depth': 'UVC STREAMOFF의 실패는 어느 반환 루프를 건너뛰며 정상 정지는 어느 순서로 버퍼를 반환합니까?',
        'callback-order': '버퍼 신호와 내부 pending_ 갱신, 요청 완료 통지 사이의 순서는 무엇입니까?',
        'callback-depth': 'Auto가 현재·수신 스레드를 비교해 Direct 즉시 호출과 Queued 메시지 전달을 고르는 분기는 무엇입니까?',
    }
    existing = {tid:[deepcopy(v) for v in visuals['sections'].get('request-lifecycle',[]) if v.get('generation')=='llm' and v['topic']==tid] for tid in questions}
    visuals['sections']['request-lifecycle'] = [v for v in visuals['sections'].get('request-lifecycle',[]) if v['topic'] not in questions]
    for topic in topics:
        additions = deepcopy(existing.get(topic['id'])) or [dict(id=topic['id']+'-flow',topic=topic['id'],kind='flow',title=topic['title']+' 그림',
                      question=questions[topic['id']],generation='llm',max_nodes=9,
                      prompt='핵심 조건과 반환 경계를 소스 구절이 지지하는 작은 그림으로 답하세요. 노드에 전체 본문을 옮기지 마세요.')]
        visuals['sections'].setdefault('request-lifecycle',[]).extend(additions)
    visual_path = ROOT/'examples/libcamera/config/visuals.yaml'
    visual_text = visual_path.read_text(encoding='utf-8')
    if 'id: preparation-depth-flow' not in visual_text:
        boundary = visual_text.index('  overview:\n')
        added = [v for v in visuals['sections']['request-lifecycle'] if v.get('generation')=='llm' and v['topic'] in questions]
        rendered = yaml.dump(added,Dumper=NoAliases,allow_unicode=True,sort_keys=False,width=105)
        visual_path.write_text(visual_text[:boundary]+''.join(('  '+line).rstrip()+'\n' for line in rendered.splitlines())+visual_text[boundary:],
                               encoding='utf-8',newline='\n')
    (RUN/'config/visuals.yaml').write_text(yaml.safe_dump(visuals,allow_unicode=True,sort_keys=False),encoding='utf-8')
    # Retain the historical full extraction and manuscripts byte-for-byte.
    shutil.copytree(BASE/'manuscripts', RUN/'manuscripts')
    facts = gzip.decompress((BASE/'facts293.json.gz').read_bytes())
    (RUN/'facts').mkdir()
    (RUN/'facts/facts.json').write_bytes(facts)
    assert json.loads(facts)['meta']['source_commit'] == COMMIT
    shutil.copytree(ROOT/'style', RUN/'current-style')
    shutil.copytree(BASE/'historical-style', RUN/'historical-style')
    shutil.copytree(BASE/'templates', RUN/'templates')
    shutil.copyfile(BASE/'site-intro.md',RUN/'site-intro.md')
    cfg = yaml.safe_load((BASE/'profiles/generation.yaml').read_bytes())
    cfg['source']['root'] = str(SOURCE)
    cfg['source']['compile_commands'] = str(RUN/'uvc-compile_commands.json')
    cfg['output'] = dict(facts_dir='facts',sdd_dir='manuscripts',diagrams_dir='manuscripts/diagrams')
    cfg['paths'] = {key:str(RUN/'config'/name) for key,name in
                    [('config',''),('sections_file','sections.yaml'),('scenarios_file','scenarios.yaml'),
                     ('consistency_file','contracts.yaml'),('glossary_file','glossary.yaml'),('products_file','products.yaml')]}
    cfg['paths'].update(prompts=str(ROOT/'examples/libcamera/prompts'),templates=str(RUN/'templates'),style=str(RUN/'current-style'))
    cfg['agent'] = dict(kind='cli',runner='codex',model='gpt-6.1-terra',command=[],
                        args=['-c','model_reasoning_effort="high"'],full_style_guides=True,
                        max_input_chars=128000,timeout_sec=600)
    cfg['site'].update(enabled=False,english_catalog=str(RUN/'english.json'),intro=str(RUN/'site-intro.md'),
                       mermaid_dir=str(PUBLIC/'docs/assets/mermaid'),manuscript_profiles={})
    cfg['visuals']['file'] = str(RUN/'config/visuals.yaml')
    cfg['publication'] = {'operation_id':'issue252-request-depth'}
    (RUN/'generation.yaml').write_text(yaml.safe_dump(cfg,allow_unicode=True,sort_keys=False),encoding='utf-8')
    review = deepcopy(cfg)
    review['agent']['max_input_chars'] = 1000000
    (RUN/'independent-review.yaml').write_text(yaml.safe_dump(review,allow_unicode=True,sort_keys=False),encoding='utf-8')
    files = [
        'src/libcamera/camera.cpp','src/libcamera/request.cpp','src/libcamera/pipeline_handler.cpp',
        'src/libcamera/pipeline/uvcvideo/uvcvideo.cpp','src/libcamera/v4l2_videodevice.cpp','src/libcamera/v4l2_device.cpp',
        'src/libcamera/framebuffer.cpp','src/libcamera/base/bound_method.cpp','src/libcamera/base/signal.cpp',
        'src/libcamera/base/object.cpp','src/libcamera/base/event_notifier.cpp','src/libcamera/base/timer.cpp',
        'include/libcamera/base/signal.h','include/libcamera/base/bound_method.h',
        'include/libcamera/internal/camera.h','include/libcamera/internal/request.h',
        'include/libcamera/internal/framebuffer.h','include/libcamera/internal/pipeline_handler.h',
        'include/libcamera/internal/v4l2_videodevice.h','Documentation/thread-safety.dox',
        'src/libcamera/base/thread.cpp','src/libcamera/base/message.cpp','src/libcamera/base/event_dispatcher_poll.cpp',
        'include/libcamera/base/thread.h','include/libcamera/base/message.h',
    ]
    windows = []
    for file in files:
        raw = git('show',COMMIT+':'+file)
        latest = git('show',HEAD+':'+file)
        assert raw == latest, 'Selected source changed at latest upstream: '+file
        path = RUN/'source-windows'/file
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(raw)
        windows.append(dict(file=file,line=1,end_line=len(raw.splitlines()),sha256=hashlib.sha256(raw).hexdigest(),latest_blob_equal=True))
    scope = yaml.safe_load((HERE/'questions.yaml').read_bytes())
    scope.update(frozen_before_generation=True, generator_base=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
                 public_base=subprocess.check_output(['git','-C',str(PUBLIC),'rev-parse','HEAD'],text=True).strip(),
                 baseline_facts_sha256=hashlib.sha256(facts).hexdigest(),
                 source_windows=windows, generation_topics=[t['id'] for t in target['design_topics']],
                 new_runtime_execution=False,human_review='pending',actual_non_author_reader_evaluation='not-run',
                 build=dict(record='build-provenance-fresh.json',record_sha256=hashlib.sha256(provenance_bytes).hexdigest(),
                            source_commit=COMMIT,status=provenance['status'],configuration=provenance['required_options'],
                            note='Actual retained build record verified before generation; full structural facts retain their original extraction.'))
    dump(RUN/'scope.json',scope)
    dump(RUN/'source-window-index.json',windows)
    print('Frozen questions, generation/review profiles and',len(windows),'whole-file sufficiency windows.',flush=True)


if __name__=='__main__':
    main()
