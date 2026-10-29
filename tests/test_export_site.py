from pathlib import Path

import pytest

from sdd.export_site import export_site
from sdd.diagrams import class_diagram
from sdd.facts.model import ClassInfo, Relation


def prepare(cfg, model):
    model.meta['source_commit'] = 'a' * 40
    model.save(cfg.facts_path)
    cfg.sections_file.write_text('''sections:
  - id: device
    output: device.md
    title: Device
    kind: prose
    facts:
      classes: [CameraDevice]
    next: {title: Details, link: nested/detail.md}
  - id: nested
    output: nested/detail.md
    title: Details
    kind: prose
    facts:
      classes: [PipeThread]
    next: {title: Device, link: device.md}
''', encoding='utf-8')
    cfg.raw['site'] = {'title': 'Test <Site>', 'source_url': 'https://github.com/example/source'}
    cfg.raw['diagrams'] = {'enabled': True}
    cfg.sdd_dir.mkdir(parents=True)
    (cfg.sdd_dir / 'nested').mkdir()
    text = '---\nsource_commit: ' + 'a' * 40 + '\nstatus: needs-review\n---\n\n'
    (cfg.sdd_dir / 'device.md').write_text(text + '# Device\n\n## Evidence\n\n'
        '`device/CameraDevice.h:40`\n\n`invented.h:99`\n\n[Details](nested/detail.md#methods)\n\n## 한글 목차\n\n[이동](#한글-목차)\n', encoding='utf-8')
    (cfg.sdd_dir / 'nested/detail.md').write_text(text + '# Details\n\n## Methods\n\n'
        '[Device](../device.md#evidence)\n', encoding='utf-8')


def test_site_preserves_verdicts_and_links_nested_pages(tmp_cfg, sample_model):
    prepare(tmp_cfg, sample_model)
    originals = {p: p.read_bytes() for p in tmp_cfg.sdd_dir.rglob('*.md')}
    out = export_site(tmp_cfg)
    doc = (out / 'device.html').read_text(encoding='utf-8')
    nested = (out / 'nested/detail.html').read_text(encoding='utf-8')
    assert 'href="nested/detail.html#methods"' in doc
    assert 'href="../device.html#evidence"' in nested
    assert 'href="../assets/reading.css?v=' in nested
    assert 'Test &lt;Site&gt;' in doc
    assert 'id="한글-목차"' in doc and 'href="#한글-목차"' in doc
    assert '사람 검토 전' in doc and 'needs-review' in doc
    assert 'https://github.com/example/source/blob/' + 'a' * 40 + '/device/CameraDevice.h#L40' in doc
    assert '<code>invented.h:99</code>' in doc
    assert '/invented.h#L99' not in doc
    assert (out / 'device.mmd').exists()
    assert 'nested/detail.html#methods' in (out / 'assets/search.json').read_text(encoding='utf-8')
    assert all(p.read_bytes() == original for p, original in originals.items())
    assert (out / 'device.md').read_bytes() == originals[tmp_cfg.sdd_dir / 'device.md']


def test_stale_facts_abort_before_publication(tmp_cfg, sample_model):
    prepare(tmp_cfg, sample_model)
    sample_model.meta['source_commit'] = 'b' * 40
    sample_model.save(tmp_cfg.facts_path)
    with pytest.raises(RuntimeError, match='commits differ'):
        export_site(tmp_cfg)
    assert not (tmp_cfg.build_dir / 'site').exists()


def test_changed_design_configuration_blocks_same_commit_publication(tmp_cfg, sample_model):
    import yaml
    from sdd.generate import Generator
    from sdd.llm import Agent
    prepare(tmp_cfg, sample_model)
    sections = tmp_cfg.sections()
    sections[0]['semantic_review'] = True
    tmp_cfg.sections_file.write_text(yaml.safe_dump({'sections': sections}), encoding='utf-8')
    Generator(tmp_cfg, sample_model, Agent(tmp_cfg.agent)).run()
    site = export_site(tmp_cfg)
    manifest = (site / 'site-manifest.json').read_bytes()
    sections[0]['answers'] = ['Changed design question']
    tmp_cfg.sections_file.write_text(yaml.safe_dump({'sections': sections}), encoding='utf-8')
    with pytest.raises(RuntimeError, match='Design evidence changed'):
        export_site(tmp_cfg)
    assert (site / 'site-manifest.json').read_bytes() == manifest
    # Removing the option must not bypass the existing page's fingerprint.
    sections[0].pop('semantic_review')
    tmp_cfg.sections_file.write_text(yaml.safe_dump({'sections': sections}), encoding='utf-8')
    with pytest.raises(RuntimeError, match='Design evidence changed'):
        export_site(tmp_cfg)


def test_diagram_has_only_extracted_relations_and_unique_node_ids(sample_model):
    sample_model.classes['other::PipeThread'] = ClassInfo('other::PipeThread')
    sample_model.relations += [Relation('PipeThread', 'CameraDevice', 'association')]
    diagram = class_diagram(sample_model, ['*PipeThread'])
    assert 'other::PipeThread' in diagram
    assert diagram.count('["PipeThread"]') == 1
    assert '상속' in diagram and 'Thread' in diagram
    assert 'CameraDevice' not in diagram  # Unselected association target is not invented/expanded.
    with pytest.raises(RuntimeError, match='narrow facts.classes'):
        class_diagram(sample_model, ['*'], limit=1)
    assert diagram == class_diagram(sample_model, ['*PipeThread'])


def test_rejects_output_path_traversal(tmp_cfg, sample_model):
    prepare(tmp_cfg, sample_model)
    tmp_cfg.sections_file.write_text('sections:\n  - output: ../escape.md\n', encoding='utf-8')
    with pytest.raises(RuntimeError, match='Invalid documentation path'):
        export_site(tmp_cfg)


def test_repeated_builds_update_relationships_without_duplicate_diagrams(tmp_cfg, sample_model):
    from sdd.generate import Generator
    from sdd.llm import Agent
    from sdd.site_build import verify_site
    prepare(tmp_cfg, sample_model)
    Generator(tmp_cfg, sample_model, Agent(tmp_cfg.agent)).run()
    markdown = (tmp_cfg.sdd_dir / 'nested/detail.md').read_text(encoding='utf-8')
    assert markdown.count('```mermaid') == 1
    out = export_site(tmp_cfg)
    first = {p.relative_to(out): p.read_bytes() for p in out.rglob('*') if p.is_file()}
    export_site(tmp_cfg)
    assert first == {p.relative_to(out): p.read_bytes() for p in out.rglob('*') if p.is_file()}
    assert (out / 'nested/detail.html').read_text(encoding='utf-8').count('class="mermaid"') == 1
    sample_model.classes['PipeThread'].bases = ['NewThreadBase']
    sample_model.save(tmp_cfg.facts_path)
    export_site(tmp_cfg)
    diagram = (out / 'nested/detail.mmd').read_text(encoding='utf-8')
    assert 'NewThreadBase' in diagram and '["Thread"]' not in diagram
    assert verify_site(out)['html_pages'] == 3


def test_removed_sections_clean_owned_artifacts_and_keep_unrelated_files(tmp_cfg, sample_model):
    import yaml
    prepare(tmp_cfg, sample_model)
    out = export_site(tmp_cfg)
    (out / 'CNAME').write_text('docs.example.org', encoding='utf-8')
    sections = yaml.safe_load(tmp_cfg.sections_file.read_text(encoding='utf-8'))
    sections['sections'] = sections['sections'][:1]
    tmp_cfg.sections_file.write_text(yaml.safe_dump(sections), encoding='utf-8')
    page = tmp_cfg.sdd_dir / 'device.md'
    page.write_text(page.read_text(encoding='utf-8').replace('[Details](nested/detail.md#methods)', ''), encoding='utf-8')
    export_site(tmp_cfg)
    assert not (out / 'nested/detail.html').exists()
    assert not (out / 'nested/detail.mmd').exists()
    assert (out / 'CNAME').read_text() == 'docs.example.org'
    assert (tmp_cfg.sdd_dir / 'nested/detail.md').exists()


def test_failed_build_preserves_previous_site(tmp_cfg, sample_model):
    prepare(tmp_cfg, sample_model)
    out = export_site(tmp_cfg)
    before = {p.relative_to(out): p.read_bytes() for p in out.rglob('*') if p.is_file()}
    tmp_cfg.raw['diagrams']['max_nodes'] = 1
    with pytest.raises(RuntimeError, match='narrow facts.classes'):
        export_site(tmp_cfg)
    assert before == {p.relative_to(out): p.read_bytes() for p in out.rglob('*') if p.is_file()}


def test_edited_artifact_is_not_silently_overwritten(tmp_cfg, sample_model):
    from sdd.site_build import verify_site
    prepare(tmp_cfg, sample_model)
    out = export_site(tmp_cfg)
    page = out / 'device.html'
    page.write_text('manual edit', encoding='utf-8')
    with pytest.raises(RuntimeError, match='manually changed'):
        export_site(tmp_cfg)
    with pytest.raises(RuntimeError, match='Artifact changed'):
        verify_site(out)
    assert page.read_text() == 'manual edit'


def test_generate_command_automatically_builds_configured_site(tmp_cfg, sample_model):
    import yaml
    from sdd.cli import main
    prepare(tmp_cfg, sample_model)
    tmp_cfg.raw['site']['enabled'] = True
    config = tmp_cfg.root / 'sdd.yaml'
    config.write_text(yaml.safe_dump(tmp_cfg.raw), encoding='utf-8')
    assert main(['--config', str(config), 'generate']) == 0
    assert (tmp_cfg.build_dir / 'site/site-manifest.json').is_file()
    assert '```mermaid' in (tmp_cfg.sdd_dir / 'device.md').read_text(encoding='utf-8')


@pytest.mark.parametrize('collision', ['nested/detail.html', 'nested'])
def test_unmanaged_output_collision_preserves_entire_destination(tmp_cfg, sample_model, collision):
    prepare(tmp_cfg, sample_model)
    out = tmp_cfg.build_dir / 'site'
    target = out / collision
    target.parent.mkdir(parents=True)
    target.write_text('operator-owned content', encoding='utf-8')
    before = {p.relative_to(out): p.read_bytes() for p in out.rglob('*') if p.is_file()}
    with pytest.raises(RuntimeError, match='Unmanaged artifact|not a directory'):
        export_site(tmp_cfg)
    assert before == {p.relative_to(out): p.read_bytes() for p in out.rglob('*') if p.is_file()}


@pytest.mark.parametrize('policy', [{'enabled': False}, {'enabled': True, 'classes': ['NoSuchClass']}])
def test_rebuild_removes_stale_managed_diagram_but_preserves_manual_mermaid(tmp_cfg, sample_model, policy):
    import yaml
    from sdd.generate import Generator
    from sdd.llm import Agent
    from sdd.site_build import verify_site
    prepare(tmp_cfg, sample_model)
    Generator(tmp_cfg, sample_model, Agent(tmp_cfg.agent)).run()
    page = tmp_cfg.sdd_dir / 'device.md'
    page.write_text(page.read_text(encoding='utf-8') + '\n```mermaid\nflowchart LR\n  ManualA --> ManualB\n```\n', encoding='utf-8')
    original = page.read_bytes()
    out = export_site(tmp_cfg)
    assert (out / 'device.mmd').exists()
    sections = yaml.safe_load(tmp_cfg.sections_file.read_text(encoding='utf-8'))
    section = sections['sections'][0]
    section['diagram'] = {'enabled': policy['enabled']}
    if 'classes' in policy:
        section['facts']['classes'] = policy['classes']
    tmp_cfg.sections_file.write_text(yaml.safe_dump(sections), encoding='utf-8')
    export_site(tmp_cfg)
    doc = (out / 'device.html').read_text(encoding='utf-8')
    assert doc.count('class="mermaid"') == 1
    assert 'ManualA' in doc
    assert not (out / 'device.mmd').exists()
    assert page.read_bytes() == original
    assert verify_site(out)['broken_links'] == 0


def test_existing_generation_without_diagram_opt_in_accepts_large_models(tmp_cfg, sample_model):
    from sdd.generate import Generator
    from sdd.llm import Agent
    for i in range(20):
        name = f'ExtraClass{i}'
        sample_model.classes[name] = ClassInfo(name)
    Generator(tmp_cfg, sample_model, Agent(tmp_cfg.agent)).run(['overview'])
    assert '<!-- sdd:class-diagram -->' not in (tmp_cfg.sdd_dir / 'overview.md').read_text(encoding='utf-8')


def prepare_groups(cfg, model):
    """group 이 있는 섹션과 시나리오 하위 페이지를 갖춘 최소 사이트."""
    model.meta['source_commit'] = 'a' * 40
    model.save(cfg.facts_path)
    cfg.sections_file.write_text('''sections:
  - id: device
    output: device.md
    title: Device
    kind: prose
    group: For Developers
    facts:
      classes: [CameraDevice]
    next: {title: Flows, link: scenarios/index.md}
  - id: scenarios
    output: scenarios/index.md
    title: Flows
    kind: per-scenario
    group: For Developers
    facts:
      scenarios: "*"
    next: {title: Pipe, link: pipe.md}
  - id: pipe
    output: pipe.md
    title: Pipe
    kind: prose
    group: For Vendors
    facts:
      classes: [PipeThread]
    next: {title: Device, link: device.md}
''', encoding='utf-8')
    cfg.scenarios_file.write_text(
        'scenarios:\n  - id: open\n    from: "CameraDevice::open()"\n'
        '  - id: capture\n    from: "CameraDevice::processCaptureRequest()"\n', encoding='utf-8')
    cfg.raw['site'] = {'title': 'Groups', 'source_url': 'https://github.com/example/source'}
    cfg.sdd_dir.mkdir(parents=True)
    (cfg.sdd_dir / 'scenarios').mkdir()
    text = '---\nsource_commit: ' + 'a' * 40 + '\nstatus: ok\n---\n\n'
    (cfg.sdd_dir / 'device.md').write_text(text + '# Device\n', encoding='utf-8')
    (cfg.sdd_dir / 'pipe.md').write_text(text + '# Pipe\n', encoding='utf-8')
    (cfg.sdd_dir / 'scenarios/index.md').write_text(text + '# Flows\n', encoding='utf-8')
    # 파일 이름 순서(capture, open)와 설정 순서(open, capture)가 다르게 둔다.
    (cfg.sdd_dir / 'scenarios/capture.md').write_text(text + '# 캡처 요청\n', encoding='utf-8')
    (cfg.sdd_dir / 'scenarios/open.md').write_text(text + '# 디바이스 오픈\n', encoding='utf-8')


def _nav_items(doc: str) -> list[str]:
    import re
    nav = re.search(r'<nav aria-label="문서 메뉴">(.*?)</nav>', doc, re.S).group(1)
    items = []
    for m in re.finditer(r'<p class="nav-group">(.*?)</p>|<a( class="nav-sub")?[^>]*>(.*?)</a>', nav):
        if m.group(1):
            items.append('[' + m.group(1) + ']')
        else:
            items.append(('  ' if m.group(2) else '') + m.group(3))
    return items


def test_메뉴는_설정한_그룹으로_나뉜다(tmp_cfg, sample_model):
    prepare_groups(tmp_cfg, sample_model)
    out = export_site(tmp_cfg)
    items = _nav_items((out / 'device.html').read_text(encoding='utf-8'))
    assert items.index('[For Developers]') < items.index('[For Vendors]')
    assert items.count('[For Developers]') == 1 and items.count('[For Vendors]') == 1
    assert items[items.index('[For Vendors]') + 1] == 'Pipe'


def test_시나리오_하위_페이지는_목차_뒤에_호출_차례로_들여쓴다(tmp_cfg, sample_model):
    prepare_groups(tmp_cfg, sample_model)
    out = export_site(tmp_cfg)
    items = _nav_items((out / 'device.html').read_text(encoding='utf-8'))
    at = items.index('Flows')
    # 파일 이름 순이면 캡처 요청이 먼저 온다. 설정 순서를 따라야 한다.
    assert items[at + 1:at + 3] == ['  디바이스 오픈', '  캡처 요청']
    # 같은 그룹 안에 있으므로 사이에 그룹 제목이 끼지 않는다.
    assert '[For Vendors]' not in items[at:at + 3]


def test_메뉴_그룹_순서는_설정이_정한다(tmp_cfg, sample_model):
    prepare_groups(tmp_cfg, sample_model)
    tmp_cfg.raw['site']['nav_groups'] = ['For Vendors', 'For Developers']
    out = export_site(tmp_cfg)
    items = _nav_items((out / 'device.html').read_text(encoding='utf-8'))
    # 섹션 순서는 device(For Developers) 가 먼저지만 메뉴는 설정을 따른다.
    assert items.index('[For Vendors]') < items.index('[For Developers]')
    # 설정에 없는 그룹은 뒤에 붙지 않고 원래 자리를 지킨다 (시작하기는 맨 앞에 끼워 넣는다).
    assert items[0] == '[시작하기]'


def test_task_sections_group_pages_and_inherit_scenarios_without_changing_manuscripts(tmp_cfg, sample_model):
    import re
    import yaml
    from sdd.site_build import verify_site
    prepare_groups(tmp_cfg, sample_model)
    sections = tmp_cfg.sections()
    sections[0]['nav_section'] = 'Understand <structure>'
    sections[1]['nav_section'] = 'Trace & diagnose'
    sections[2]['group'] = 'For Developers'
    sections[2]['nav_section'] = 'Understand <structure>'
    tmp_cfg.sections_file.write_text(yaml.safe_dump({'sections': sections}), encoding='utf-8')
    before = {p: p.read_bytes() for p in tmp_cfg.sdd_dir.rglob('*.md')}
    out = export_site(tmp_cfg)
    doc = (out / 'scenarios/open.html').read_text(encoding='utf-8')
    nav = re.search(r'<nav aria-label="문서 메뉴">(.*?)</nav>', doc, re.S)[1]
    tasks = re.findall(r'<section class="nav-section"[^>]*>(.*?)</section>', nav, re.S)
    assert len(tasks) == 2
    assert '<h2>Understand &lt;structure&gt;</h2>' in tasks[0]
    assert 'device.html' in tasks[0] and 'pipe.html' in tasks[0]
    assert 'scenarios/' not in tasks[0]
    assert '<h2>Trace &amp; diagnose</h2>' in tasks[1]
    assert '<details class="nav-branch" open>' in tasks[1]
    assert 'href="index.html"' in tasks[1] and 'href="open.html" aria-current="page"' in tasks[1]
    assert tasks[1].endswith('</details>')
    assert doc.count('<section class="nav-section"') == 2
    assert before == {p: p.read_bytes() for p in tmp_cfg.sdd_dir.rglob('*.md')}
    first = (out / 'site-manifest.json').read_bytes()
    export_site(tmp_cfg)
    assert (out / 'site-manifest.json').read_bytes() == first
    assert verify_site(out)['broken_links'] == 0


def test_하위_문서는_접었다_펼_수_있다(tmp_cfg, sample_model):
    prepare_groups(tmp_cfg, sample_model)
    out = export_site(tmp_cfg)
    parent = (out / 'scenarios/index.html').read_text(encoding='utf-8')
    other = (out / 'device.html').read_text(encoding='utf-8')
    child = (out / 'scenarios/open.html').read_text(encoding='utf-8')
    assert '<summary>하위 문서 2 편</summary>' in other
    # 읽고 있는 가지만 펴 둔다. 다른 문서에서는 접어서 목록을 짧게 유지한다.
    assert '<details class="nav-branch" open>' in parent
    assert '<details class="nav-branch" open>' in child
    assert '<details class="nav-branch">' in other
    # 접기는 하위 문서만 감싼다. 같은 그룹의 다른 문서가 안으로 들어가면 안 된다.
    branch = other.split('<details class="nav-branch">')[1].split('</details>')[0]
    assert 'scenarios/open.html' in branch and 'pipe.html' not in branch


def test_task_sections_end_before_unclassified_pages_and_reader_groups(tmp_cfg, sample_model):
    import re
    import yaml
    prepare_groups(tmp_cfg, sample_model)
    sections = tmp_cfg.sections()
    sections[0]['nav_section'] = sections[2]['nav_section'] = 'Shared task'
    tmp_cfg.sections_file.write_text(yaml.safe_dump({'sections': sections}), encoding='utf-8')
    out = export_site(tmp_cfg)
    doc = (out / 'device.html').read_text(encoding='utf-8')
    nav = re.search(r'<nav aria-label="문서 메뉴">(.*?)</nav>', doc, re.S)[1]
    tasks = re.findall(r'<section class="nav-section"[^>]*>(.*?)</section>', nav, re.S)
    assert len(tasks) == 2
    assert all('<h2>Shared task</h2>' in task for task in tasks)
    assert 'device.html' in tasks[0] and 'pipe.html' not in tasks[0]
    assert 'pipe.html' in tasks[1] and 'device.html' not in tasks[1]
    assert all('nav-group' not in task and 'scenarios/' not in task for task in tasks)
    assert 'scenarios/index.html' in nav and '<details class="nav-branch">' in nav


def test_소스_링크_형식은_호스트_설정을_따른다(tmp_cfg, sample_model):
    prepare(tmp_cfg, sample_model)
    tmp_cfg.raw['site']['source_url'] = 'https://gerrit.example.com/plugins/gitiles/hal'
    tmp_cfg.raw['site']['source_link'] = 'gitiles'
    out = export_site(tmp_cfg)
    doc = (out / 'device.html').read_text(encoding='utf-8')
    assert ('https://gerrit.example.com/plugins/gitiles/hal/+/' + 'a' * 40
            + '/device/CameraDevice.h#40') in doc
    assert '/blob/' not in doc
    # facts 에 없는 인용은 형식과 무관하게 링크하지 않는다.
    assert '<code>invented.h:99</code>' in doc


def test_소스_링크_템플릿을_직접_지정할_수_있다(tmp_cfg, sample_model):
    prepare(tmp_cfg, sample_model)
    tmp_cfg.raw['site']['source_link_template'] = '{url}/browse/{file}?at={commit}#{line}'
    out = export_site(tmp_cfg)
    doc = (out / 'device.html').read_text(encoding='utf-8')
    assert ('https://github.com/example/source/browse/device/CameraDevice.h?at='
            + 'a' * 40 + '#40') in doc


def test_잘못된_소스_링크_설정은_즉시_실패한다(tmp_cfg, sample_model):
    prepare(tmp_cfg, sample_model)
    tmp_cfg.raw['site']['source_link'] = 'bitbucket'
    with pytest.raises(RuntimeError, match='source_link'):
        export_site(tmp_cfg)
    tmp_cfg.raw['site'].pop('source_link')
    tmp_cfg.raw['site']['source_link_template'] = '{url}/blob/{branch}/{file}'
    with pytest.raises(RuntimeError, match='자리표시자'):
        export_site(tmp_cfg)


def test_mermaid_dir_는_사이트에_동봉되고_CDN_주소가_남지_않는다(tmp_cfg, sample_model):
    prepare(tmp_cfg, sample_model)
    vendored = tmp_cfg.root / 'assets' / 'mermaid'
    (vendored / 'chunks' / 'mermaid.esm.min').mkdir(parents=True)
    (vendored / 'mermaid.esm.min.mjs').write_text('export default {};', encoding='utf-8')
    (vendored / 'chunks' / 'mermaid.esm.min' / 'chunk-1.mjs').write_text('// chunk', encoding='utf-8')
    tmp_cfg.raw['site']['mermaid_dir'] = 'assets/mermaid'
    out = export_site(tmp_cfg)
    assert (out / 'assets/mermaid/mermaid.esm.min.mjs').is_file()
    assert (out / 'assets/mermaid/chunks/mermaid.esm.min/chunk-1.mjs').is_file()
    doc = (out / 'device.html').read_text(encoding='utf-8')
    assert '"mermaid": "assets/mermaid/mermaid.esm.min.mjs"' in doc
    assert 'cdn.jsdelivr.net' not in doc


def test_mermaid_dir_에_본체가_없으면_실패한다(tmp_cfg, sample_model):
    prepare(tmp_cfg, sample_model)
    (tmp_cfg.root / 'assets' / 'mermaid').mkdir(parents=True)
    tmp_cfg.raw['site']['mermaid_dir'] = 'assets/mermaid'
    with pytest.raises(RuntimeError, match='fetch-mermaid'):
        export_site(tmp_cfg)


def test_사이트는_승인_상태를_구분해_보여준다(tmp_cfg, sample_model):
    from sdd import approvals
    prepare(tmp_cfg, sample_model)
    ledger = approvals.load(tmp_cfg)
    approvals.approve_page(ledger, 'device.md',
                           (tmp_cfg.sdd_dir / 'device.md').read_text(encoding='utf-8'), by='검토자')
    approvals.save(tmp_cfg, ledger)
    out = export_site(tmp_cfg)
    device = (out / 'device.html').read_text(encoding='utf-8')
    detail = (out / 'nested/detail.html').read_text(encoding='utf-8')
    index = (out / 'index.html').read_text(encoding='utf-8')
    assert '사람 검토 승인 · 검토자' in device
    assert '사람 검토 전' in detail
    assert '사람 검토 승인 · 검토자' in index and '사람 검토 전' in index


def test_require_approval_은_미승인_문서의_게시를_차단한다(tmp_cfg, sample_model):
    from sdd import approvals
    prepare(tmp_cfg, sample_model)
    tmp_cfg.raw['site']['require_approval'] = True
    with pytest.raises(RuntimeError, match='require_approval'):
        export_site(tmp_cfg)
    assert not (tmp_cfg.build_dir / 'site' / 'device.html').exists()
    ledger = approvals.load(tmp_cfg)
    for rel in ('device.md', 'nested/detail.md'):
        approvals.approve_page(ledger, rel, (tmp_cfg.sdd_dir / rel).read_text(encoding='utf-8'), by='검토자')
    approvals.save(tmp_cfg, ledger)
    out = export_site(tmp_cfg)
    assert (out / 'device.html').is_file()
    # 승인 이후 본문이 바뀌면(stale) 다시 차단한다.
    page = tmp_cfg.sdd_dir / 'device.md'
    page.write_text(page.read_text(encoding='utf-8') + '\n추가 문장.\n', encoding='utf-8')
    with pytest.raises(RuntimeError, match='require_approval'):
        export_site(tmp_cfg)


def test_configured_next_overrides_menu_order_and_preserves_anchor(tmp_cfg, sample_model):
    import yaml
    prepare(tmp_cfg, sample_model)
    sections = tmp_cfg.sections()
    sections[0]['next']['link'] = 'device.md#evidence'
    tmp_cfg.sections_file.write_text(yaml.safe_dump({'sections': sections}), encoding='utf-8')
    out = export_site(tmp_cfg)
    page = (out / 'device.html').read_text(encoding='utf-8')
    assert '<a class="next" href="device.html#evidence">' in page


def test_redundant_navigation_table_is_removed_without_changing_data_tables(tmp_cfg, sample_model):
    prepare(tmp_cfg, sample_model)
    path = tmp_cfg.sdd_dir / 'device.md'
    with path.open('a', encoding='utf-8') as f:
        f.write('\n| 지금 확인할 내용 | 이동할 절 |\n|---|---|\n| 확인합니다. | [근거](#evidence) |\n')
        f.write('\n| 데이터 | 값 |\n|---|---|\n| 상태 | 정상 |\n')
    out = export_site(tmp_cfg)
    page = (out / 'device.html').read_text(encoding='utf-8')
    assert '지금 확인할 내용' not in page
    assert '<td>확인합니다.</td>' not in page
    assert page.count('class="table-scroll"') == 1


def test_wide_tables_stack_with_column_labels_on_phones(tmp_cfg, sample_model):
    prepare(tmp_cfg, sample_model)
    with (tmp_cfg.sdd_dir / 'device.md').open('a', encoding='utf-8') as f:
        f.write('\n| 클래스 | `prepare()`의 처리 | 책임 "주석" |\n|---|---|---|\n| A | b | c |\n| D | | f |\n')
    out = export_site(tmp_cfg)
    page = (out / 'device.html').read_text(encoding='utf-8')
    assert page.count('class="table-scroll stack"') == 1
    assert '<td data-label="클래스">A</td>' in page
    assert '<td data-label="prepare()의 처리">b</td>' in page
    assert '<td data-label="책임 &quot;주석&quot;">c</td>' in page
    assert '<td data-label="prepare()의 처리"></td>' in page
    css = (out / 'assets/reading.css').read_text(encoding='utf-8')
    assert 'table{min-width:500px}' not in css and '.stack td::before{content:attr(data-label)' in css


def test_page_state_uses_plain_words_and_keeps_status_code_in_evidence(tmp_cfg, sample_model):
    prepare(tmp_cfg, sample_model)
    path = tmp_cfg.sdd_dir / 'device.md'
    path.write_text(path.read_text(encoding='utf-8').replace(
        'status: needs-review', 'status: ok\ngeneration_method: source-bound-contract'), encoding='utf-8')
    out = export_site(tmp_cfg)
    page = (out / 'device.html').read_text(encoding='utf-8')
    state = page.split('<div class="page-state">', 1)[1].split('</div>', 1)[0]
    assert '<code>' not in state
    assert '자동 검사 통과' in state and '작성: 코드 발췌와 대조한 설명' in state
    assert 'href="#page-evidence"' in state
    evidence = page.split('id="page-evidence"', 1)[1]
    assert '<dt>자동 검사</dt><dd>통과 (<code>ok</code>).' in evidence
    assert '소스 발췌에 연결한 설계 설명' in evidence
    index = (out / 'index.html').read_text(encoding='utf-8')
    assert '<code>ok</code>' not in index and '<code>needs-review</code>' not in index
    assert '>인용 검사 확인 필요</td>' in index
