import json
import re

import pytest

from sdd.export_site import export_site
from sdd.site_build import verify_site
from sdd.site_localization import DisplayText, display_strings, english_diagram, source_hash
from test_export_site import prepare


def bilingual(cfg, model):
    prepare(cfg, model)
    out = export_site(cfg)
    pages, units = {}, set()
    for path in out.rglob('*.html'):
        text = path.read_text(encoding='utf-8')
        pages[path.relative_to(out).as_posix()] = source_hash(text)
        units.update(display_strings(text))
    for entry in json.loads((out / 'assets/search.json').read_text(encoding='utf-8')):
        units.update(entry[k] for k in ('title', 'page') if re.search('[가-힣]', entry[k]))
    catalog = {'schema': 1, 'pages': pages,
               'strings': {s: 'English ' + ' '.join(re.findall(r'\{\{\d+\}\}', s)) for s in units}}
    path = cfg.root / 'english.json'
    path.write_text(json.dumps(catalog), encoding='utf-8')
    cfg.raw['site']['english_catalog'] = 'english.json'
    return out, path, catalog


def test_bilingual_routes_search_sources_and_repeatability(tmp_cfg, sample_model):
    out, _, _ = bilingual(tmp_cfg, sample_model)
    originals = {p: p.read_bytes() for p in tmp_cfg.sdd_dir.rglob('*.md')}
    export_site(tmp_cfg)
    en = (out / 'en/nested/detail.html').read_text(encoding='utf-8')
    assert '<html lang="en">' in en
    assert 'href="../../nested/detail.html"' in en
    assert 'href="../device.html#evidence"' in en
    assert 'href="../../assets/reading.css"' in en
    assert 'href="../../nested/detail.md"' in en
    assert 'src="../../assets/site.js"' in en
    assert 'human review pending' in en
    assert 'class="language-selector"' in en
    assert 'href="en/device.html"' in (out / 'device.html').read_text(encoding='utf-8')
    assert (out / 'en/device.mmd').read_text() == english_diagram((out / 'device.mmd').read_text(encoding='utf-8'))
    search = json.loads((out / 'en/assets/search.json').read_text())
    assert any(x['url'].endswith('#%ED%95%9C%EA%B8%80-%EB%AA%A9%EC%B0%A8') for x in search)
    assert all(not re.search('[가-힣]', x['title']) for x in search)
    assert verify_site(out)['html_pages'] == 6
    first = {p: p.read_bytes() for p in out.rglob('*') if p.is_file()}
    export_site(tmp_cfg)
    assert all(p.read_bytes() == data for p, data in first.items())
    assert all(p.read_bytes() == data for p, data in originals.items())
    assert 'english_catalog' in json.loads((out / 'site-manifest.json').read_text())['inputs']


@pytest.mark.parametrize('failure', ['source', 'missing', 'placeholder', 'schema'])
def test_translation_failure_preserves_published_site(tmp_cfg, sample_model, failure):
    out, path, catalog = bilingual(tmp_cfg, sample_model)
    export_site(tmp_cfg)
    before = {p: p.read_bytes() for p in out.rglob('*') if p.is_file()}
    if failure == 'source':
        source = tmp_cfg.sdd_dir / 'device.md'
        source.write_text(source.read_text(encoding='utf-8') + '\nChanged English context.\n', encoding='utf-8')
    elif failure == 'missing':
        catalog['strings'] = {}
    elif failure == 'placeholder':
        key = next(k for k in catalog['strings'] if '{{' in k)
        catalog['strings'][key] = 'Missing inline evidence'
    else:
        catalog['schema'] = 2
    path.write_text(json.dumps(catalog), encoding='utf-8')
    with pytest.raises(RuntimeError, match='English'):
        export_site(tmp_cfg)
    assert all(p.read_bytes() == data for p, data in before.items())


def test_inline_translation_can_reorder_links_but_cannot_inject_markup():
    text = '<p><code>foo&lt;T&gt;</code>를 <a href="x#고정">확인</a>하세요.</p><pre>원문 &amp; code</pre><script>{"x":"a&b"}</script>'
    strings = {'확인': 'check', '{{0}}를 {{2}}하세요.': '{{2}} {{0}} <script>bad</script>'}
    parser = DisplayText(lambda s: strings[s])
    parser.feed(text)
    result = ''.join(parser.output)
    assert '<a href="x#고정">check</a> <code>foo&lt;T&gt;</code>' in result
    assert '&lt;script&gt;bad&lt;/script&gt;' in result
    assert '<pre>원문 &amp; code</pre>' in result
    assert '<script>{"x":"a&b"}</script>' in result


@pytest.mark.parametrize('mermaid', ['https://example.test/mermaid.mjs?a=1&b=2', 'assets/mermaid.mjs'])
def test_mermaid_asset_resolution(tmp_cfg, sample_model, mermaid):
    out, path, catalog = bilingual(tmp_cfg, sample_model)
    # Catalog binding includes the Mermaid setting; refresh it deliberately.
    tmp_cfg.raw['site'].pop('english_catalog')
    tmp_cfg.raw['site']['mermaid'] = mermaid
    export_site(tmp_cfg)
    catalog['pages'] = {p.relative_to(out).as_posix(): source_hash(p.read_text(encoding='utf-8')) for p in out.rglob('*.html')}
    path.write_text(json.dumps(catalog), encoding='utf-8')
    tmp_cfg.raw['site']['english_catalog'] = 'english.json'
    export_site(tmp_cfg)
    en = (out / 'en/index.html').read_text(encoding='utf-8')
    config = json.loads(re.search(r'id="site-config" type="application/json">(.*?)</script>', en)[1])
    assert config['mermaid'] == (mermaid if mermaid.startswith('https:') else '../' + mermaid)


def test_translation_does_not_inherit_human_approval(tmp_cfg, sample_model):
    from sdd.site_localization import localize_site
    out, _, _ = bilingual(tmp_cfg, sample_model)
    tmp_cfg.raw['site']['require_approval'] = True
    with pytest.raises(RuntimeError, match='no human approval ledger'):
        localize_site(tmp_cfg, out)


def test_english_route_collision_is_rejected(tmp_cfg, sample_model):
    from sdd.site_localization import localize_site
    out, _, _ = bilingual(tmp_cfg, sample_model)
    (out / 'en').mkdir()
    (out / 'en/index.html').write_text('<p>Existing document</p>')
    with pytest.raises(RuntimeError, match='reserved'):
        localize_site(tmp_cfg, out)


def test_diagram_translation_preserves_topology():
    source = 'flowchart LR\n a["상속"]\n a -.->|상속| b\n a -.->|"stop() · 예약된 호출, 실행 순서는 정적으로 확인 불가"| b'
    en = english_diagram(source)
    assert 'a["상속"]' in en
    assert 'a -.->|inheritance| b' in en
    assert '"stop() · dispatched method; execution order not established statically"' in en
