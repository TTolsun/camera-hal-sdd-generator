import json
import subprocess

import yaml

from sdd.carryover import carry_forward
from sdd.evidence import collect, contract_text, fingerprint, topic_blocks
from sdd.facts.model import ClassInfo, KnowledgeModel, Location, Relation
from sdd.generate import Generator
from sdd.semantic import review


def test_inheritance_object_is_not_mistaken_for_the_derived_subject():
    model = KnowledgeModel(classes={'ns::Base': ClassInfo('ns::Base'),
                                    'ns::Driver': ClassInfo('ns::Driver')})
    for phrase in ('`Base`를 상속한 파생 클래스', '`Base`를 상속하는 클래스', '`Base`를 직접 상속받은 클래스'):
        text = '`Driver::configure`의 구현자는 ' + phrase + '에 저장된 커스텀 필드에 의존할 수 있습니다. `x.h:1`'
        assert review(text, model, {'x.h:1'}) == []


def test_inverse_inheritance_word_order_still_checks_the_named_child():
    model = KnowledgeModel(classes={'ns::Base': ClassInfo('ns::Base'),
                                    'ns::Child': ClassInfo('ns::Child')})
    text = '`Base`를 상속한 `Child` 클래스가 필드를 보관합니다. `x.h:1`'
    assert any('상속' in finding for finding in review(text, model, {'x.h:1'}))
    model.classes['ns::Child'].bases = ['ns::Base']
    assert review(text, model, {'x.h:1'}) == []


def test_revision_pinned_excerpts_and_fail_closed_anchors(tmp_cfg):
    root = tmp_cfg.source_root
    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args], encoding='utf-8').strip()
    git('init')
    (root / 'camera.cpp').write_text('old\nSTART\ncontract\nEND\n', encoding='utf-8')
    git('add', '.')
    git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'fixture')
    m = KnowledgeModel(meta={'source_commit': git('rev-parse', 'HEAD')})
    source = dict(id='source', file='camera.cpp', start='START', end='END')
    topic = dict(id='state', sources=[source])
    sec = dict(id='camera', design_topics=[topic])
    tmp_cfg.sections_file.write_text(yaml.safe_dump({'sections': [sec]}), encoding='utf-8')
    (root / 'camera.cpp').write_text('dirty unrelated checkout', encoding='utf-8')
    collect(tmp_cfg, m)
    assert m.evidence['camera/state/source']['text'] == 'START\ncontract\nEND'
    assert 'camera.cpp:2' in m.citations()
    assert not topic_blocks(m, 'camera', topic)[1]
    assert KnowledgeModel.from_dict(m.to_dict()).evidence == m.evidence
    source['sha256'] = m.evidence['camera/state/source']['sha256']
    tmp_cfg.sections_file.write_text(yaml.safe_dump({'sections': [sec]}), encoding='utf-8')
    (root / 'camera.cpp').write_text('old\nSTART\nchanged contract\nEND\n', encoding='utf-8')
    git('add', '.')
    git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'changed source')
    m.meta['source_commit'] = git('rev-parse', 'HEAD')
    collect(tmp_cfg, m)
    assert m.evidence['camera/state/source']['status'] == 'needs-review'
    assert not m.citations()
    source['start'] = 'missing'
    assert topic_blocks(m, 'camera', topic)[1]
    tmp_cfg.sections_file.write_text(yaml.safe_dump({'sections': [sec]}), encoding='utf-8')
    collect(tmp_cfg, m)
    assert topic_blocks(m, 'camera', topic)[1]
    assert not m.citations()


def test_source_bound_contract_requires_matching_hash_and_preserves_unknowns(tmp_cfg):
    source = dict(id='stop', file='x.cpp', start='start', end='end', sha256='original')
    topic = dict(id='shutdown', sources=[source], statements=[
        dict(text='종료는 동기적으로 요청을 반환합니다.', evidence=['stop'])])
    model = KnowledgeModel(meta={'source_commit': 'abc'}, evidence={
        'camera/shutdown/stop': dict(commit='abc', selector=source, status='available',
                                     file='x.cpp', line=7, sha256='original')})
    text, gaps = contract_text(model, 'camera', topic)
    assert not gaps and text.endswith('`x.cpp:7`')
    model.evidence['camera/shutdown/stop']['sha256'] = 'changed'
    text, gaps = contract_text(model, 'camera', topic)
    assert gaps and text.startswith('확인 필요:') and '동기적으로' not in text


def test_structural_overgeneralization_wrong_namespace_and_missing_evidence():
    m = KnowledgeModel(classes={'ns::Active': ClassInfo('ns::Active'),
                                'ns::Frame': ClassInfo('ns::Frame', bases=['Base'])})
    supplied = {'x.h:1'}
    assert review('`ns::Active`와 `ns::Frame`은 모두 상속합니다 `x.h:1`.', m, supplied)
    assert review('`wrong::Active`의 상태입니다 `x.h:1`.', m, supplied)
    assert review('`ns::Frame`은 `ns::Active`를 상속합니다 `x.h:1`.', m, supplied)
    assert review('요청을 반환합니다 `x.h:2`.', m, supplied)
    assert review('요청을 반환합니다.', m, supplied)
    assert not review('`ns::Active`의 직접 기반 클래스는 없습니다 `x.h:1`.', m, supplied)
    assert review('`ns::Active` 클래스는 현재 facts에서 존재하지 않으므로 확인해야 합니다 `x.h:1`.', m, supplied)
    assert not review('`ns::Missing` 클래스는 현재 facts에서 추출되지 않았습니다 `x.h:1`.', m, supplied)
    assert review('`ns::Active`는 `ns::Frame`에 필드 참조를 갖습니다 `x.h:1`.', m, supplied)
    m.relations.append(Relation('ns::Active', 'ns::Frame', 'association'))
    assert not review('`ns::Active`는 `ns::Frame`에 필드 참조를 갖습니다 `x.h:1`.', m, supplied)
    assert not review('`ns::Frame`은 `Base`를 직접 상속받습니다 `x.h:1`.', m, supplied)
    assert not review('`ns::Active`는 상태를 보유하며, `ns::Frame`은 `Base`를 상속받습니다 `x.h:1`.', m, supplied)


def test_changed_relationship_blocks_carryover_even_at_same_line(tmp_cfg, sample_model):
    sec = dict(id='camera', semantic_review=True, facts={'classes': ['CameraDevice']})
    tmp_cfg.sections_file.write_text(yaml.safe_dump({'sections': [sec]}), encoding='utf-8')
    tmp_cfg.sdd_dir.mkdir()
    path = tmp_cfg.sdd_dir / 'camera.md'
    old = fingerprint(sample_model, sec)
    path.write_text(f'---\nsection: camera\nsource_commit: old\nagent: fake\nevidence_fingerprint: {old}\n---\n'
                    '`device/CameraDevice.h:40`\n', encoding='utf-8')
    sample_model.classes['CameraDevice'].bases.append('ChangedBase')
    promoted, stale = carry_forward(tmp_cfg, sample_model, [])
    assert not promoted and stale
    assert 'source_commit: old' in path.read_text(encoding='utf-8')


def test_missing_topic_remains_visible_without_llm(tmp_cfg, sample_model):
    sec = dict(id='camera', title='카메라', output='camera.md', design_topics=[
        dict(id='shutdown', title='종료 계약', question='언제 종료합니까?', sources=[
            dict(id='stop', file='missing.cpp', start='start', end='end')])])
    tmp_cfg.sections_file.write_text(yaml.safe_dump({'sections': [sec]}), encoding='utf-8')
    class NoCalls:
        def chat(self, *args, **kwargs):
            raise AssertionError('Missing evidence must not trigger invention')
    Generator(tmp_cfg, sample_model, NoCalls()).run()
    text = (tmp_cfg.sdd_dir / 'camera.md').read_text(encoding='utf-8')
    assert '## 종료 계약' in text and '확인 필요' in text and 'status: needs-review' in text
    report = json.loads((tmp_cfg.build_dir / 'content-review.json').read_text(encoding='utf-8'))
    assert report['sections']['camera_shutdown']['status'] == 'needs-review'


def test_generator_retries_structural_error_and_records_review(tmp_cfg, sample_model):
    from sdd.budget import Block
    tmp_cfg.agent.kind = 'fake'
    good = ('`CameraDevice`에는 추출된 직접 기반 클래스가 없습니다 `device/CameraDevice.h:40`. '
            '요청 처리의 실행 스레드와 버퍼 수명은 이 선언만으로 확정할 수 없으므로 추가 확인이 필요합니다 '
            '`device/CameraDevice.h:40`.')
    bad = good.replace('추출된 직접 기반 클래스가 없습니다', '기반 클래스를 상속하는 구조가 있습니다')
    class Replies:
        def __init__(self):
            self.calls = []
        def chat(self, system, user, tag=''):
            self.calls.append(user)
            return bad if len(self.calls) == 1 else good
    agent = Replies()
    generator = Generator(tmp_cfg, sample_model, agent)
    _, _, verdict = generator._ask('camera', {'semantic_review': True}, '카메라',
                                   [Block('class', 'CameraDevice `device/CameraDevice.h:40`', 1)], 'STALE_ABSENCE_CLAIM')
    assert verdict.ok and len(agent.calls) == 2
    assert '상속을 주장' in agent.calls[1]
    assert all('STALE_ABSENCE_CLAIM' not in user for user in agent.calls)


def test_fact_narration_tracks_added_and_removed_relationships_without_llm(tmp_cfg, sample_model):
    sec = dict(id='structure', title='구조', narration='facts', facts={'classes': ['CameraDevice', 'FrameFactory']})
    tmp_cfg.sections_file.write_text(yaml.safe_dump({'sections': [sec]}), encoding='utf-8')
    class NoCalls:
        def chat(self, *args, **kwargs):
            raise AssertionError('Structure must be rendered from facts')
    gen = Generator(tmp_cfg, sample_model, NoCalls())
    path = gen.run()[0]
    before = path.read_text(encoding='utf-8')
    sample_model.relations.append(Relation('CameraDevice', 'FrameFactory', 'association'))
    gen.run()
    after = path.read_text(encoding='utf-8')
    assert '필드 참조 관계가 추출되었습니다.' not in before
    assert '`FrameFactory`에 대한 필드 참조 관계가 추출되었습니다.' in after
    sample_model.relations.clear()
    gen.run()
    assert '필드 참조 관계가 추출되었습니다.' not in path.read_text(encoding='utf-8')


def test_fingerprint_tracks_package_and_scenario_inputs(sample_model):
    sec = dict(id='overview', semantic_review=True, facts={'packages': ['*'], 'reading_order': 'process_capture_request'})
    original = fingerprint(sample_model, sec)
    sample_model.packages['device'].classes.append('NewClass')
    assert fingerprint(sample_model, sec) != original
    original = fingerprint(sample_model, sec)
    sample_model.scenarios['process_capture_request'].messages[0].name = 'changedCall'
    assert fingerprint(sample_model, sec) != original


def test_default_output_name_still_enforces_publication_fingerprint(tmp_cfg, sample_model):
    import pytest
    from sdd.export_site import export_site
    sec = dict(id='structure', title='구조', narration='facts', facts={'classes': ['CameraDevice']},
               next={'title': '구조', 'link': 'structure.md'})
    tmp_cfg.sections_file.write_text(yaml.safe_dump({'sections': [sec]}), encoding='utf-8')
    sample_model.save(tmp_cfg.facts_path)
    Generator(tmp_cfg, sample_model, None).run()
    export_site(tmp_cfg)
    sample_model.classes['CameraDevice'].bases.append('NewBase')
    sample_model.save(tmp_cfg.facts_path)
    with pytest.raises(RuntimeError, match='Design evidence changed'):
        export_site(tmp_cfg)


def test_메뉴_분류만_바꾸면_지문이_그대로다(sample_model):
    """group·nav_section·routes·next·watch 는 페이지 배치와 영향 분석에만 쓰인다.

    이것만 바꿔도 지문이 달라지면, 메뉴 라벨 한 줄 때문에 근거가 고정된 문서를 모델로 다시
    만들어야 한다. 게시 문서의 문장이 이유 없이 바뀐다.
    """
    sec = dict(id='camera', semantic_review=True, title='카메라',
               facts={'classes': ['CameraDevice']}, next={'title': '다음', 'link': 'a.md'})
    original = fingerprint(sample_model, sec)
    moved = dict(sec, group='For Vendors', nav_section='연동 구현', routes=[{'q': '확인합니다.', 'to': '#절'}],
                 next={'title': '다른 문서', 'link': 'b.md'}, watch=['src/**'])
    assert fingerprint(sample_model, moved) == original


def test_설명에_쓰는_설정이_바뀌면_지문이_달라진다(sample_model):
    sec = dict(id='camera', semantic_review=True, title='카메라', facts={'classes': ['CameraDevice']})
    original = fingerprint(sample_model, sec)
    assert fingerprint(sample_model, dict(sec, title='카메라 모델')) != original
    assert fingerprint(sample_model, dict(sec, reader='다른 독자')) != original
    assert fingerprint(sample_model, dict(sec, answers=['무엇을 책임집니까?'])) != original
    assert fingerprint(sample_model, dict(sec, facts={'classes': ['PipeThread']})) != original
    assert fingerprint(sample_model, dict(sec, lead='먼저 확인하세요.')) != original


def test_A6_이어지는_설명은_한_문단으로_묶고_인용은_문단_끝에_한_번씩만_모은다():
    from sdd.evidence import _paragraphs
    entries = [
        ('behavior', '`start()`는 카메라를 시작합니다.', ['`a.cpp:1`']),
        ('behavior', '시작 전에는 구성이 끝나 있어야 합니다.', ['`a.cpp:1`', '`a.cpp:9`']),
        ('behavior', '정지하면 요청이 완료됩니다.', ['`b.cpp:5`']),
        ('limitation', '실행에서 확인할 항목입니다.', ['`c.cpp:2`']),
        ('limitation', '또 다른 확인 항목입니다.', ['`c.cpp:3`']),
    ]
    assert _paragraphs(entries) == [
        '`start()`는 카메라를 시작합니다. 시작 전에는 구성이 끝나 있어야 합니다. 정지하면 요청이 완료됩니다. '
        '`a.cpp:1`, `a.cpp:9`, `b.cpp:5`',
        '실행 확인 항목: 실행에서 확인할 항목입니다. `c.cpp:2`',
        '실행 확인 항목: 또 다른 확인 항목입니다. `c.cpp:3`',
    ]


def test_A6_문단은_네_문장과_길이_상한을_넘지_않는다():
    from sdd.evidence import _paragraphs, PARAGRAPH_SENTENCES, PARAGRAPH_CHARS
    entries = [('behavior', f'{i}번째 설명입니다.', [f'`a.cpp:{i}`']) for i in range(9)]
    paragraphs = _paragraphs(entries)
    assert [p.count('설명입니다.') for p in paragraphs] == [PARAGRAPH_SENTENCES, PARAGRAPH_SENTENCES, 1]
    long = [('behavior', '가' * (PARAGRAPH_CHARS - 20) + '입니다.', ['`a.cpp:1`']), ('behavior', '나' * 40 + '입니다.', ['`a.cpp:2`'])]
    assert len(_paragraphs(long)) == 2


def test_ordered_actions_keep_individual_citations_and_end_before_scope_note():
    from sdd.evidence import _paragraphs
    from sdd.site_markdown import _render
    entries=[('behavior','1. 환경을 확인합니다.',['`a.cpp:1`']),
             ('behavior','2. 변경 승인을 받습니다.',['`a.cpp:2`']),
             ('limitation','장치 실행은 별도로 확인합니다.',['`a.cpp:3`'])]
    body='\n\n'.join(_paragraphs(entries))
    document=_render(body,'trial.md',set(),None,'','abc')[0]
    assert document.count('<ol>')==1 and document.count('<li>')==2
    assert document.index('</ol>') < document.index('실행 확인 항목:')
    assert all(f'a.cpp:{i}' in document for i in [1,2,3])


def test_A6_이전_배치의_원고도_검증을_통과한다():
    from sdd.evidence import _paragraphs
    entries = [('behavior', '첫 설명입니다.', ['`a.cpp:1`']), ('behavior', '둘째 설명입니다.', ['`a.cpp:2`'])]
    assert _paragraphs(entries, grouped=False) == ['첫 설명입니다. `a.cpp:1`', '둘째 설명입니다. `a.cpp:2`']
    assert len(_paragraphs(entries)) == 1
