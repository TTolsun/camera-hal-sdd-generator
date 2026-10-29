import re

from sdd.index_navigation import index_navigation


def table(kind, name, line):
    return (f'<table><thead><tr><th>{kind}</th><th>선언 위치</th></tr></thead>'
            f'<tbody><tr><td><code>{name}</code></td><td><a href="https://code/src#L{line}">'
            f'<code>src/device.h:{line}</code></a></td></tr></tbody></table>')


def test_index_rows_preserve_code_citations_and_get_unique_stable_destinations():
    source = ('<h2 id="api">api</h2>' + table('클래스', 'Device&lt;T&gt;', 4)
              + table('함수', 'start()', 10) + table('함수', 'start()', 11)
              + '<h2 id="driver">driver</h2>' + table('클래스', 'Device&lt;T&gt;', 4))
    rendered, entries = index_navigation(source, 'nested/index.html', 'Components')
    anchors = re.findall(r'<tr id="([^"]+)" tabindex="-1" data-symbol-kind="([^"]+)">', rendered)
    assert len(anchors) == len(entries) == 4
    assert len({anchor for anchor, _ in anchors}) == 4
    assert [kind for _, kind in anchors] == ['class', 'function', 'function', 'class']
    assert [row['title'] for row in entries] == ['Device<T>', 'start()', 'start()', 'Device<T>']
    assert all(row['kind'] == 'symbol' and row['page'] == 'Components' for row in entries)
    assert [row['url'] for row in entries] == ['nested/index.html#' + anchor for anchor, _ in anchors]
    assert re.findall(r'href="([^"]+)"', rendered) == re.findall(r'href="([^"]+)"', source)
    assert '<code>Device&lt;T&gt;</code>' in rendered
    assert index_navigation(source, 'nested/index.html', 'Components') == (rendered, entries)
    added, added_entries = index_navigation('<h2>other</h2>' + table('클래스', 'Unrelated', 1) + source,
                                             'nested/index.html', 'Components')
    assert [row['url'] for row in added_entries[1:]] == [row['url'] for row in entries]
    _, moved_entries = index_navigation(source.replace('src/device.h:4', 'src/device.h:44'),
                                        'nested/index.html', 'Components')
    assert [row['url'] for row in moved_entries] == [row['url'] for row in entries]


def test_navigation_tables_and_code_examples_do_not_become_symbols():
    source = '<h2>Guide</h2>' + table('시작할 문서', 'Guide', 1) + '<pre>&lt;table&gt;클래스&lt;/table&gt;</pre>'
    assert index_navigation(source, 'index.html', 'Guide') == (source, [])


def test_duplicate_rows_and_unicode_identifiers_keep_inspectable_unique_links():
    source = '<h2>src/한글</h2>' + table('클래스', '카메라', 1) * 2
    rendered, entries = index_navigation(source, 'index.html', '색인')
    assert entries[0]['title'] == entries[1]['title'] == '카메라'
    assert entries[1]['url'] == entries[0]['url'] + '-2'
    assert rendered.count('<code>카메라</code>') == 2


def test_export_indexes_symbols_without_rewriting_manuscripts(tmp_cfg, sample_model):
    import json
    from sdd.generate import Generator
    from sdd.llm import Agent
    from sdd.export_site import export_site
    from sdd.site_build import verify_site

    sample_model.meta['source_commit'] = 'a' * 40
    sample_model.save(tmp_cfg.facts_path)
    tmp_cfg.sections_file.write_text('sections:\n  - id: components\n    title: Components\n    kind: per-package\n    narration: facts\n    facts: {classes: ["*"]}\n    output: components.md\n    next: {title: Components, link: components.md}\n', encoding='utf-8')
    Generator(tmp_cfg, sample_model, Agent(tmp_cfg.agent)).run()
    manuscript = (tmp_cfg.sdd_dir/'components.md').read_bytes()
    out = export_site(tmp_cfg)
    document = (out/'components.html').read_text(encoding='utf-8')
    search = json.loads((out/'assets/search.json').read_text(encoding='utf-8'))
    symbols = [row for row in search if row.get('kind') == 'symbol']
    assert symbols and all('components.html#symbol-' in row['url'] for row in symbols)
    assert '"index": true' in document
    assert 'assets/reader-tools.js?v=' in document
    assert (tmp_cfg.sdd_dir/'components.md').read_bytes() == manuscript
    assert 'index_navigation.py' in json.loads((out/'site-manifest.json').read_text(encoding='utf-8'))['engine']
    assert verify_site(out)['broken_links'] == 0


def test_english_search_keeps_unicode_symbol_identifiers(tmp_cfg):
    import json
    from sdd.site_localization import localize_site, source_hash

    out = tmp_cfg.root/'site'
    (out/'assets').mkdir(parents=True)
    document = ('<html lang="ko"><head></head><body><div class="header-actions"></div>'
                '<article><h1>색인</h1><code>카메라</code></article></body></html>')
    (out/'index.html').write_text(document, encoding='utf-8')
    (out/'assets/search.json').write_text(json.dumps([dict(title='카메라', page='색인',
        url='index.html#symbol-1111111111111111', kind='symbol')]), encoding='utf-8')
    catalog = tmp_cfg.root/'english.json'
    catalog.write_text(json.dumps(dict(schema=1,pages={'index.html': source_hash(document)},
        strings={'색인':'Index','카메라':'Wrong symbol translation'})), encoding='utf-8')
    tmp_cfg.raw['site'] = {'english_catalog': str(catalog)}
    localize_site(tmp_cfg,out)
    symbol = json.loads((out/'en/assets/search.json').read_text(encoding='utf-8'))[0]
    assert symbol['title'] == '카메라' and symbol['page'] == 'Index'
    assert '<code>카메라</code>' in (out/'en/index.html').read_text(encoding='utf-8')
