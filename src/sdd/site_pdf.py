"""Render static downloads from the finished print views, using only staged assets."""
from __future__ import annotations

from io import BytesIO
import mimetypes
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

from .site_paths import owned_path


def _stable_table_headers(pdf, pikepdf):
    """Keep accessible table relationships without Chromium's session-specific DOM node IDs."""
    tree = pdf.Root.get('/StructTreeRoot')
    if tree is None or '/IDTree' not in tree:
        return
    ids = pikepdf.NameTree(tree.IDTree)
    stable = pikepdf.NameTree.new(pdf)
    names = {}
    for index, (key, element) in enumerate(ids.items()):
        name = f'header-{index:08d}'
        names[key] = name
        element.ID = name
        stable[name] = element
    tree.IDTree = stable.obj
    for obj in pdf.objects:
        if not isinstance(obj, pikepdf.Dictionary) or obj.get('/S') not in ('/TH', '/TD'):
            continue
        attributes = obj.get('/A', [])
        if isinstance(attributes, pikepdf.Dictionary):
            attributes = [attributes]
        for attr in attributes:
            if isinstance(attr, pikepdf.Dictionary) and '/Headers' in attr:
                attr.Headers = [names[str(value)] for value in attr.Headers]


def render_pdfs(root: Path, views: list[str], public_url: str) -> None:
    try:
        import pikepdf
        from playwright.sync_api import Error, sync_playwright
    except ImportError as exc:
        raise RuntimeError('PDF downloads require the pdf extra. Install with uv sync --extra pdf.') from exc

    base = (public_url or 'https://sdd.invalid').rstrip('/') + '/'
    origin = urlsplit(base)
    failures = []

    def serve(route):
        url = urlsplit(route.request.url)
        if (url.scheme, url.netloc) == (origin.scheme, origin.netloc) and url.path.startswith(origin.path):
            path = owned_path(root, unquote(url.path[len(origin.path):]))
            if path.is_file():
                mime = ('application/javascript' if path.suffix in {'.js', '.mjs'}
                        else mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
                route.fulfill(path=path, content_type=mime)
                return
        failures.append(route.request.url)
        route.abort()

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch()
        except Error as exc:
            raise RuntimeError('Cannot start Chromium for PDF downloads. Run '
                               'python -m playwright install chromium --only-shell.') from exc
        context = browser.new_context(locale='en-US', service_workers='block')
        context.route('**/*', serve)
        for view in views:
            target = owned_path(root, view).with_suffix('.pdf')
            if target.exists():
                raise RuntimeError(f'PDF download path already in use: {target.name}')
            page = context.new_page()
            try:
                page.goto(base + quote(view))
                page.wait_for_function("document.querySelector('#print-document')?.disabled === false",
                                       timeout=120_000)
                if failures or page.locator('.mermaid:not([data-ready="true"]), .mermaid:not(:has(svg))').count():
                    raise RuntimeError(f'Missing PDF assets or diagrams in {view}. Bundle site.mermaid_dir. '
                                       + ', '.join(failures[:3]))
                page.emulate_media(media='print')
                # Mermaid gives SVGs 100% width, which can enlarge a narrow, tall
                # diagram beyond the sheet. Fit both dimensions using its viewBox.
                page.evaluate("""() => { for (const svg of document.querySelectorAll('.mermaid svg')) {
                    const {width, height} = svg.viewBox.baseVal;
                    svg.style.width = Math.min(width, 700 * width / height) + 'px';
                } }""")
                page.evaluate('async () => { await document.fonts.ready; '
                              'await Promise.all(Array.from(document.images, image => image.decode())); }')
                if not public_url:
                    page.evaluate("""() => { for (const a of document.querySelectorAll('a[href]')) {
                        if (a.origin === location.origin && a.pathname !== location.pathname)
                            a.removeAttribute('href');
                    } }""")
                data = page.pdf(format='A4', print_background=True, tagged=True,
                                margin=dict.fromkeys(('top', 'right', 'bottom', 'left'), '12mm'))
                with pikepdf.Pdf.open(BytesIO(data)) as pdf:
                    _stable_table_headers(pdf, pikepdf)
                    for field in ('/CreationDate', '/ModDate'):
                        if field in pdf.docinfo:
                            del pdf.docinfo[field]
                    pdf.save(target, deterministic_id=True)
            except Error as exc:
                raise RuntimeError(f'Could not render PDF for {view}: {exc}') from exc
            finally:
                page.close()
        browser.close()
