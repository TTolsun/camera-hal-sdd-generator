import re

import pytest

from sdd.export_site import export_site
from sdd.full_document import is_combined, to_markdown
from sdd.site_build import verify_site

from test_export_site import prepare


def test_whole_document_holds_every_page_with_internal_links(tmp_cfg, sample_model):
    prepare(tmp_cfg, sample_model)
    out = export_site(tmp_cfg)
    combined = (out / 'download/full.html').read_text(encoding='utf-8')
    pages = re.findall(r'<section class="full-page" id="doc-(\d+)">', combined)
    assert len(pages) == 3  # index, device, nested/detail
    # Links between pages land inside the one document; IDs stay unique per page.
    device = next(n for n in pages if f'id="d{n}-evidence"' in combined)
    nested = next(n for n in pages if f'id="d{n}-methods"' in combined)
    assert f'href="#d{nested}-methods"' in combined and f'href="#d{device}-evidence"' in combined
    assert 'href="nested/detail.html' not in combined and 'id="한글-목차"' not in combined
    # Folded review records and source excerpts are printed open.
    assert re.search(r'<details(?![^>]*\sopen)', combined) is None
    assert 'a' * 40 in combined and 'Test &lt;Site&gt; · 전체 문서' in combined
    assert 'href="../assets/reading.css?v=' in combined and 'mermaid.render(`sdd-print-' in combined
    # The long body is hidden while drawing and always shown again afterwards.
    assert "body.style.display = 'none'" in combined
    assert re.search(r"finally \{\s*body\.style\.display = '';", combined)
    # Every diagram on the site is in the copy.
    diagrams = sum(p.read_text(encoding='utf-8').count('class="mermaid"')
                   for p in out.rglob('*.html') if 'download' not in p.relative_to(out).parts)
    assert diagrams and combined.count('class="mermaid"') == diagrams
    verify_site(out)


def test_whole_document_markdown_and_download_menu(tmp_cfg, sample_model):
    prepare(tmp_cfg, sample_model)
    out = export_site(tmp_cfg)
    markdown = (out / 'download/full.md').read_text(encoding='utf-8')
    assert markdown.startswith('# Test <Site> · 전체 문서'.replace('<', '\\<').replace('>', '\\>'))
    assert '# Device' in markdown and '# Details' in markdown
    assert markdown.count('```mermaid') == (out / 'download/full.html').read_text(encoding='utf-8').count('class="mermaid"')
    # In-document links keep a visible target.
    targets = set(re.findall(r'\]\(#([^)]+)\)', markdown))
    anchors = set(re.findall(r'<a id="([^"]+)"></a>', markdown))
    assert targets and targets <= anchors
    assert 'https://github.com/example/source/blob/' + 'a' * 40 + '/device/CameraDevice.h#L40' in markdown
    page = (out / 'nested/detail.html').read_text(encoding='utf-8')
    assert page.count('popovertarget="download-menu"') == 1
    assert 'id="download-menu" popover="auto"' in page and 'aria-hidden="true"' in page
    assert '현재 페이지' in page and 'href="../download/pages/nested/detail.html?print"' in page
    assert 'href="../download/pages/nested/detail.md" download="detail.md"' in page
    current = (out / 'download/pages/nested/detail.html').read_text(encoding='utf-8')
    current_md = (out / 'download/pages/nested/detail.md').read_text(encoding='utf-8')
    assert current.count('class="full-page"') == 1 and '<h1>Details</h1>' in current
    assert '<h1>Device</h1>' not in current and '# Details' in current_md and '# Device' not in current_md
    assert 'href="../../../device.html#evidence"' in current
    assert 'href="../../../nested/detail.html"' in current
    assert 'href="../../../assets/reading.css?v=' in current
    assert 'href="../download/full.html?print"' in page and 'href="../download/full.md" download="Test-Site.md"' in page


def test_whole_document_can_be_turned_off(tmp_cfg, sample_model):
    prepare(tmp_cfg, sample_model)
    tmp_cfg.raw['site']['full_document'] = False
    out = export_site(tmp_cfg)
    assert not (out / 'download').exists()
    assert 'download-menu' not in (out / 'device.html').read_text(encoding='utf-8')


def test_combined_page_is_excluded_from_per_page_audits():
    assert is_combined('download/full.html') and is_combined('en/download/full.html')
    assert not is_combined('download.html') and not is_combined('scenarios/full.html')


def test_markdown_conversion_keeps_structure_and_text():
    source = '''<h2 id="x">Title *star* snake_case _lead</h2>
<p>See <a href="#x">here</a> and <a href="https://e.com/a b">out</a> and <a href="local.json">file</a>.</p>
<div class="table-scroll"><table><thead><tr><th>Name</th><th>Note</th></tr></thead>
<tbody><tr><td><code>a|b</code></td><td>one<br>two</td></tr></tbody></table></div>
<table><tr><td><ul><li>nested</li></ul></td></tr></table>
<ul><li>first<ul><li>child</li></ul></li><li><p>para</p><pre><code class="language-cpp">int x;</code></pre></li></ul>
<details class="note"><summary>Folded</summary><p>hidden text</p></details>
<dl><dt>Commit</dt><dd><code>abc</code></dd></dl>
<pre class="mermaid">flowchart LR
  A[Start] --> B</pre>
<pre><code>has ``` fence</code></pre>
<p>1. not a list</p>'''
    markdown = to_markdown(source)
    assert '## <a id="x"></a>Title \\*star\\* snake_case \\_lead' in markdown
    assert '[here](#x)' in markdown and '[out](<https://e.com/a b>)' in markdown
    assert 'file.' in markdown and 'local.json' not in markdown
    assert '| `a\\|b` | one<br>two |' in markdown
    assert '<table><tbody><tr><td><ul><li>nested</li></ul></td></tr></tbody></table>' in markdown
    assert '- first\n\n  - child\n- para' in markdown and '```cpp\n  int x;\n  ```' in markdown
    assert '<details open>\n<summary>Folded</summary>\n\nhidden text\n\n</details>' in markdown
    assert '- **Commit**: `abc`' in markdown
    assert '```mermaid\nflowchart LR\n  A[Start] --> B\n```' in markdown
    assert '````\nhas ``` fence\n````' in markdown
    assert '1\\. not a list' in markdown
    assert to_markdown('<p>x</p>', base_url='https://s.example/site/download/').strip() == 'x'
    assert '[file](https://s.example/site/local.json)' in to_markdown(
        '<a href="../local.json">file</a>', base_url='https://s.example/site/download/')


def test_markdown_conversion_refuses_to_drop_text(monkeypatch):
    from sdd import full_document
    monkeypatch.setattr(full_document._Markdown, 'definitions', lambda self, node: [])
    with pytest.raises(RuntimeError, match='omit text: Commit'):
        to_markdown('<dl><dt>Commit</dt><dd>abc</dd></dl>')


def test_whole_document_keeps_shared_site_assets_unchanged(tmp_cfg, sample_model):
    """Changing shared CSS/JS would send every reviewed visual item back to review."""
    prepare(tmp_cfg, sample_model)
    tmp_cfg.raw['site']['full_document'] = False
    out = export_site(tmp_cfg)
    before = {p.relative_to(out).as_posix(): p.read_bytes() for p in (out / 'assets').rglob('*') if p.is_file()}
    tmp_cfg.raw['site']['full_document'] = True
    export_site(tmp_cfg)
    after = {p.relative_to(out).as_posix(): p.read_bytes() for p in (out / 'assets').rglob('*') if p.is_file()}
    assert before == after


def test_visual_review_reuse_ignores_only_the_exact_download_menu(tmp_cfg, sample_model):
    """The menu is page chrome; a changed menu or extra content must still count as a change."""
    from sdd.visual_audit import Document, canonical
    from sdd.visual_review_reuse import presentation_normalizer
    prepare(tmp_cfg, sample_model)
    tmp_cfg.raw['site']['full_document'] = False
    out = export_site(tmp_cfg)
    without = (out / 'device.html').read_text(encoding='utf-8')
    tmp_cfg.raw['site']['full_document'] = True
    export_site(tmp_cfg)
    with_menu = (out / 'device.html').read_text(encoding='utf-8')

    def normalized(text):
        document = Document(text)
        presentation_normalizer()(document, 'device.html')
        return canonical(document.root)

    assert without != with_menu and normalized(without) == normalized(with_menu)
    edited = with_menu.replace('.pdf</a>', '.pdf copy</a>', 1)
    assert normalized(edited) != normalized(without)

@pytest.mark.parametrize('english', [False, True])
def test_static_pdf_downloads_link_to_both_scopes(tmp_cfg, sample_model, monkeypatch, english):
    from sdd.full_document import publish
    import shutil

    prepare(tmp_cfg, sample_model)
    tmp_cfg.raw['site']['full_document'] = False
    out = export_site(tmp_cfg)
    prefix = 'en/' if english else ''
    if english:
        (out / 'en/nested').mkdir(parents=True)
        shutil.copyfile(out / 'nested/detail.html', out / 'en/nested/detail.html')

    def renderer(root, views, public_url):
        for view in views:
            source = root / view
            assert source.is_file()
            source.with_suffix('.pdf').write_bytes(b'%PDF-test')

    monkeypatch.setattr('sdd.site_pdf.render_pdfs', renderer)
    publish(out, [('Details', '', 'nested/detail.md')], site_title='Manual', pdf_downloads=True)
    menu = (out / (prefix + 'nested/detail.html')).read_text(encoding='utf-8')
    ext = '.en.pdf' if english else '.pdf'
    for path, name in [('pages/nested/detail', 'detail'), ('full', 'Manual')]:
        assert f'href="../download/{path}.pdf" download="{name}{ext}"' in menu
        assert (out / (prefix + 'download') / (path + '.pdf')).is_file()
    assert '?print' not in menu


def test_pdf_table_ids_follow_reading_order_with_reversed_browser_ids():
    pdf_lib = pytest.importorskip('pikepdf')
    from sdd.site_pdf import _stable_table_headers

    with pdf_lib.Pdf.new() as pdf:
        ids = pdf_lib.NameTree.new(pdf)
        headers = []
        for browser_id in ('node20', 'node10'):
            header = pdf.make_indirect(pdf_lib.Dictionary(S=pdf_lib.Name.TH, ID=browser_id))
            ids[browser_id] = header
            headers.append(header)
        cell = pdf.make_indirect(pdf_lib.Dictionary(S=pdf_lib.Name.TD,
                                  A=pdf_lib.Dictionary(Headers=['node20', 'node10'])))
        pdf.Root.StructTreeRoot = pdf_lib.Dictionary(IDTree=ids.obj, K=[*headers, cell])

        _stable_table_headers(pdf, pdf_lib)

        assert [str(h.ID) for h in headers] == ['header-00000000', 'header-00000001']
        assert list(cell.A.Headers) == [h.ID for h in headers]
        stable = pdf_lib.NameTree(pdf.Root.StructTreeRoot.IDTree)
        assert stable['header-00000000'].objgen == headers[0].objgen
