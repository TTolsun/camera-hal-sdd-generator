"""Prepare a fixed public addBuffer question before any inference is run.

This isolated sample does not replace the full published camera-requests page.
It reuses archived public facts at their original commit and preserves that
provenance. No new extraction/build/runtime claim is made for those facts.
"""
from copy import deepcopy
import argparse
import gzip
import hashlib
import json
from pathlib import Path

import yaml


def prepare(work, source, public):
    root = Path(__file__).resolve().parents[4]
    work, source, public = work.resolve(), source.resolve(), public.resolve()
    if work.exists():
        raise ValueError('The sample directory already exists; preserve the previous execution')
    baseline = '293d751a814e0d4c34e85ad457ccd9d5eefd1a61'
    archive = public/'publication/issue214/facts293.json.gz'
    facts = gzip.decompress(archive.read_bytes())
    model = json.loads(facts)
    if model['meta']['source_commit'] != baseline:
        raise ValueError('Unexpected archived source commit')
    original = yaml.safe_load((root/'examples/libcamera/config/sections.yaml').read_text(encoding='utf-8'))
    section = deepcopy(next(s for s in original['sections'] if s['id'] == 'camera-requests'))
    topic = deepcopy(next(t for t in section['design_topics'] if t['id'] == 'request'))
    part = deepcopy(next(p for p in topic['parts'] if p['id'] == 'buffer-rejection'))
    selector = deepcopy(model['evidence']['camera-requests/request/buffer-code']['selector'])
    record = model['evidence']['camera-requests/request/buffer-code']
    lines = (source/record['file']).read_text(encoding='utf-8').splitlines()
    excerpt = '\n'.join(lines[record['line']-1:record['end_line']])
    if excerpt != record['text']:
        raise ValueError('Current fixed source bytes differ from the archived question window')
    topic.update(question=part['question'], title='addBuffer의 검사 순서와 연결 경계',
                 answer_contract=part['answer_contract'], sources=[selector], covers=['request'],
                 max_statements=part['max_statements'])
    topic.pop('parts')
    section.update(title='addBuffer 발행 계약 검증 표본',
        lead='addBuffer의 거절 조건과 요청·버퍼 연결 경계를 확인합니다.', facts={},
        design_topics=[topic], design_requirements=[dict(id='request', question=part['question'])],
        routes=[], next=dict(title='발행 계약 검증 표본', link='camera-requests.md'))
    section.pop('semantic_review', None)
    def proof(quote):
        if record['text'].count(quote) != 1:
            raise ValueError('Diagram quote is not unique in the fixed source window')
        return [dict(source='request/buffer-code', sha256=record['sha256'], quote=quote)]
    stream = 'if (!stream) {'
    fence = 'if (buffer->_d()->fence()) {'
    duplicate = 'if (!inserted) {'
    linked = 'buffer->_d()->setRequest(this);\n\t_d()->pending_.insert(buffer);'
    def node(ident, ko, en, quote, decision=False):
        value = dict(id=ident, label=ko, label_en=en, evidence=proof(quote))
        if decision:
            value['shape'] = 'decision'
        return value
    def edge(start, end, ko, en, quote):
        return dict(**{'from': start, 'to': end}, label=ko, label_en=en, evidence=proof(quote))
    diagram = dict(id='buffer-rejection', topic='request', kind='decision',
        title='세 거절 검사와 요청 연결',
        question='stream·잔존 fence·중복 stream 검사와 요청 연결까지만 다루며, 이후 전달받은 fence의 이동은 제외합니다.',
        nodes=[node('stream', 'stream이 null인가?', 'Is stream null?', stream, True),
               node('invalid', '-EINVAL로 거절', 'Reject with -EINVAL', 'return -EINVAL;'),
               node('fence', 'buffer에 fence가 남았는가?', 'Does buffer retain a fence?', fence, True),
               node('stale', '잔존 fence: -EEXIST', 'Retained fence: -EEXIST', "Can't add buffer that still references a fence"),
               node('duplicate', 'stream 등록이 중복됐는가?', 'Is the stream already registered?', duplicate, True),
               node('exists', '중복 stream: -EEXIST', 'Duplicate stream: -EEXIST', 'FrameBuffer already set for stream'),
               node('linked', 'setRequest와 pending_에 연결', 'Bind with setRequest and pending_', linked)],
        edges=[edge('stream','invalid','예','Yes',stream), edge('stream','fence','아니요','No',stream),
               edge('fence','stale','예','Yes',fence), edge('fence','duplicate','아니요','No',fence),
               edge('duplicate','exists','예','Yes',duplicate), edge('duplicate','linked','아니요','No',linked)])
    base = yaml.safe_load((root/'examples/libcamera/sdd.yaml').read_text(encoding='utf-8'))
    agent = deepcopy(base['agent'])
    cfg = dict(source=dict(root=str(source), compile_commands=str(source/'build/compile_commands.json'),
                           exclude=base['source']['exclude']),
        output=dict(facts_dir='facts', sdd_dir='manuscripts', diagrams_dir='manuscripts/diagrams'),
        paths=dict(sections_file='sections.yaml', scenarios_file='scenarios.yaml',
                   prompts=str(root/'examples/libcamera/prompts'), templates=str(root/'templates'),
                   style=str(root/'style'), consistency_profile='review.yaml'),
        agent=agent, review=deepcopy(base['review']),
        visuals=dict(file='visuals.yaml'),
        site=dict(title='libcamera 발행 계약 검증 표본', english_catalog='english.json',
                  source_url='https://github.com/TTolsun/libcamera-sdd'),
        publication=dict(operation_id='issue241-public-buffer-rejection', operation_file='operation.json'))
    work.mkdir(parents=True)
    (work/'facts').mkdir()
    (work/'facts/facts.json').write_bytes(facts)
    for name, data in (('sdd.yaml', cfg), ('review.yaml', dict(agent=deepcopy(agent))),
                       ('sections.yaml', dict(sections=[section])), ('scenarios.yaml', dict(scenarios=[])),
                       ('visuals.yaml', dict(schema=1, sections={'camera-requests': [diagram]}))):
        (work/name).write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding='utf-8')
    execution = {k: deepcopy(agent.get(k, [] if k in ('command', 'args') else ''))
                 for k in ('kind', 'runner', 'model', 'command', 'args')}
    # The caller must replace this prerequisite with the real final test report
    # and its exact hash before any generation can begin.
    operation = dict(schema=1, revision=1, reason='Validate the fixed public addBuffer reader question.',
        sections=['camera-requests'], completion=['Validate source-bound Korean and English output.',
             'Keep actual CLI receipts, history, independent review and public deployment evidence.'],
        excluded=['Full reader/visual audit #163/#215.', 'Reuse decisions #242.', 'Failure diagnosis #243.'],
        source_commit=baseline, profiles={k: deepcopy(execution) for k in ('generation', 'translation', 'review')},
        prerequisites=[dict(path='policy-ready.json', gate='before-generation', producer='final-policy-tests',
                            sha256='0'*64, bindings=dict(status='passed', stage='policy-integration'))], discoveries=[])
    (work/'operation.json').write_text(json.dumps(operation, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    plan = dict(schema=1, baseline=baseline, section='camera-requests', topic='request',
        question=part['question'], source=record,
        profiles=operation['profiles'], facts_archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
        comparison=['prerequisite-missing', 'first-execution', 'same-basis-resume', 'reasoned-revision'],
        collection='generation-runs, immutable publication plans and original CLI receipts',
        limits='Existing public profile limits only; no new work-wide token/time/call limits.',
        scope='Isolated fixed reader question, not completion of the whole published handbook.')
    (work/'comparison-plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(work)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--public', type=Path, required=True)
    options = parser.parse_args()
    prepare(options.work, options.source, options.public)
