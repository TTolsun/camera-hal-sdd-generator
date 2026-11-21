"""Exercise the reader edition through the normal staged publication path."""

import json

import pytest
import yaml

from sdd.export_site import export_site
from sdd.reader_edition import _fragment, _parse, _first, _section, _render, section_digest
from sdd.site_build import verify_site


def configure(cfg):
    cfg.raw['site'] = {'reader_edition': 'reader.yaml', 'title': 'Test SDD'}
    cfg.sections_file.write_text('''sections:
  - id: base
    output: base.md
    title: Original
    kind: manual
  - id: detail
    output: nested/detail.md
    title: Detail
    kind: manual
''', encoding='utf-8')
    source = cfg.sdd_dir / 'base.md'
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text('''# Original

## Use this {#task}

[More](nested/detail.md#support). [Earlier detail](#archived).

## More detail {#archived}

ARCHIVED TECHNICAL DETAILS.
''', encoding='utf-8')
    detail = cfg.sdd_dir / 'nested/detail.md'
    detail.parent.mkdir()
    detail.write_text('# Detail\n\n## Support {#support}\n\nRuntime condition.\n', encoding='utf-8')
    data = {'schema': 1,
            'groups': [{'id': 'start', 'ko': '시작', 'en': 'Start'}, {'id': 'vendor', 'ko': 'Vendor', 'en': 'Vendor'}],
            'pages': [{'path': 'index.md', 'group': 'start', 'ko': '홈', 'en': 'Home',
                       'links': [{'path': 'tasks/support.md#new-support', 'ko': '지원 선택', 'en': 'Choose support'}],
                       'sections': [{'source': 'base.md', 'fragment': 'task', 'id': 'reader-task'}]},
                      {'path': 'tasks/support.md', 'group': 'vendor', 'ko': '지원', 'en': 'Support',
                       'sections': [{'source': 'nested/detail.md', 'fragment': 'support', 'id': 'new-support'}]}],
            'aliases': {'base.md': 'index.md', 'nested/detail.md': 'tasks/support.md#new-support'}}
    return data, detail


def save(cfg, data):
    (cfg.root / 'reader.yaml').write_text(yaml.safe_dump(data, allow_unicode=True), encoding='utf-8')


def test_edition_projects_sections_and_keeps_earlier_addresses(tmp_cfg):
    data, _ = configure(tmp_cfg)
    save(tmp_cfg, data)
    root = export_site(tmp_cfg)
    assert verify_site(root)['manifest_verified']
    home = (root / 'index.html').read_text(encoding='utf-8')
    assert home.index('class="reader-start"') < home.index('class="mobile-toc"')
    assert 'id="reader-task"' in home and 'href="tasks/support.html#new-support"' in home
    assert 'ARCHIVED TECHNICAL DETAILS' not in home
    assert 'reader-archive/base.html#archived' in home
    old = (root / 'base.html').read_text(encoding='utf-8')
    assert 'id="task"><a href="index.html#reader-task"' in old
    assert 'id="archived"><a href="reader-archive/base.html#archived"' in old
    assert '<article>' not in old
    archived = (root / 'reader-archive/base.html').read_text(encoding='utf-8')
    assert 'ARCHIVED TECHNICAL DETAILS' in archived
    assert 'id="task"><a href="../index.html#reader-task"' in archived
    assert '<h2 id="task">' not in archived and '<details class="mobile-toc"' not in archived
    report = json.loads((root / 'reader-edition.json').read_text(encoding='utf-8'))
    assert set(report['pages']) == {'index.html', 'tasks/support.html'}
    assert 'base.html' in report['compatibility']
    search = json.loads((root / 'assets/search.json').read_text(encoding='utf-8'))
    assert {item['url'] for item in search} == {'index.html', 'index.html#reader-task',
                                                  'tasks/support.html', 'tasks/support.html#new-support'}
    assert 'ARCHIVED TECHNICAL DETAILS' not in (root / 'download/full.md').read_text(encoding='utf-8')


def test_edition_table_pin_rejects_stale_displayed_conditions(tmp_cfg):
    data, detail = configure(tmp_cfg)
    fragment = _fragment()
    article = _first(_parse('<article><h2>Support</h2><p>Runtime condition.</p></article>'), tag='article')
    for child in article.childNodes:
        fragment.appendChild(child.cloneNode(deep=True))
    page = data['pages'][1]
    page['table'] = {lang: [['Category', 'Condition'], ['Test', 'Runtime']] for lang in ('ko', 'en')}
    page['table_source'] = {'source': 'nested/detail.md', 'fragment': 'support',
                            'sha256': {lang: section_digest(fragment) for lang in ('ko', 'en')}}
    save(tmp_cfg, data)
    root = export_site(tmp_cfg)
    before = (root / 'site-manifest.json').read_bytes()
    detail.write_text(detail.read_text(encoding='utf-8').replace('Runtime condition.', 'Changed condition.'), encoding='utf-8')
    with pytest.raises(ValueError, match='ko table evidence changed'):
        export_site(tmp_cfg)
    assert (root / 'site-manifest.json').read_bytes() == before


def test_overlapping_address_keeps_scripts_outside_readable_main(tmp_cfg):
    data, _ = configure(tmp_cfg)
    tmp_cfg.raw['site']['intro'] = 'intro.md'
    (tmp_cfg.root / 'intro.md').write_text('# Earlier home\n\n## Earlier detail {#earlier}\n\nPreserved detail.\n',
                                           encoding='utf-8')
    save(tmp_cfg, data)
    root = export_site(tmp_cfg)
    home = (root / 'index.html').read_text(encoding='utf-8')
    readable, after = home.split('</main>', 1)
    assert 'id="earlier"><a href="reader-archive/index.html#earlier"' in readable
    assert 'data-reader-compatibility' not in readable and 'reader-compatibility.js' not in readable
    assert 'data-reader-compatibility' in after and 'async' not in after
    assert '<script defer src="assets/reader-compatibility.js"></script>' in after


def test_section_cuts_preserve_adjacent_mermaid_markers_and_selected_children():
    source = '''<article>
<h2 id="parent">Parent</h2><p>Lead.</p>
<!-- sdd:visual:keep -->
<h3 id="child">Keep child</h3><p>Keep explanation.</p>
<!-- /sdd:visual:keep -->
<!-- sdd:visual:omit -->
<h3 id="omitted">Omitted</h3><p>Omitted explanation.</p>
<!-- /sdd:visual:omit -->
<!-- sdd:class-diagram -->
<h2 id="next">Next</h2><p>Next explanation.</p>
<!-- /sdd:class-diagram -->
</article>'''
    article = _first(_parse(source), tag='article')

    def rendered(selection):
        fragment = _fragment()
        for node in _section(article, {'source': 'base.md', **selection}):
            fragment.appendChild(node.cloneNode(deep=True))
        return _render(fragment)

    chosen = rendered({'fragment': 'parent', 'children': ['child']})
    assert 'Lead.' in chosen and 'Keep explanation.' in chosen
    assert '<!-- sdd:visual:keep -->' in chosen and '<!-- /sdd:visual:keep -->' in chosen
    assert 'visual:omit' not in chosen and 'class-diagram' not in chosen
    child = rendered({'fragment': 'child'})
    assert '<!-- sdd:visual:keep -->' in child and '<!-- /sdd:visual:keep -->' in child
    assert 'Lead.' not in child and 'visual:omit' not in child
    following = rendered({'fragment': 'next'})
    assert '<!-- sdd:class-diagram -->' in following and '<!-- /sdd:class-diagram -->' in following
