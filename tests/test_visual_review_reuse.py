import hashlib
import html
import json
import subprocess

import pytest

from sdd.visual_audit import apply_reviews, inventory_page, policy
from sdd.visual_review_reuse import carry_reviews, reuse_published
from test_visual_audit import FIGURE, document, ledger


def inventory(body, *, relative=False):
    options = policy()
    return dict(items=inventory_page(document(body), 'guide.html', options,
                                     source_commit='a' * 40, section_relative=relative),
                policy=options, errors=[])


def reuse(before, after, *, previous_ledger=None):
    original = inventory(before)
    return carry_reviews(previous_ledger or ledger(original), original, inventory(after),
                         inventory(before, relative=True), inventory(after, relative=True),
                         baseline_build='old-build', stable_pages={'guide.html'})


def test_only_unchanged_anchored_sections_and_their_source_windows_are_carried():
    before = ('<h2 id="first">First</h2><p>First answer.</p>'
              '<h2 id="second">Second</h2><p>Use <a class="citation" href="#code">the source</a>.</p>'
              '<h3 id="evidence">Evidence</h3><pre id="code">Exact source.</pre>')
    after = before.replace('<h2 id="second">', '<p>New condition.</p><h2 id="second">')
    original = ledger(inventory(before))
    original['items']['guide.html#second'].update(
        source_windows=['guide.html#code'], review_method='independent-cli', reviewer_receipt='original-receipt')
    updated, stats = reuse(before, after, previous_ledger=original)
    assert stats['position_only'] == 2
    assert stats['pending'] == ['guide.html#$heading-0', 'guide.html#first']
    record = updated['items']['guide.html#second']
    assert record['reviewer_receipt'] == 'original-receipt'
    assert record['review_method'] == 'independent-cli'
    assert record['source_windows'] == ['guide.html#code']
    assert record['position_reuse']['previous_fingerprint'] == original['items']['guide.html#second']['fingerprint']
    applied = apply_reviews(inventory(after), updated)
    assert applied['unresolved'] == 2
    assert applied['items'][2]['position_reuse']['baseline_build_id'] == 'old-build'


@pytest.mark.parametrize(('old', 'new'), [
    ('Exact source.', 'Changed source.'),
    ('<pre id="code">', '<pre id="code" hidden>'),
    ('Keep <span>A</span><span hidden>B</span>', 'Keep <span hidden>A</span><span>B</span>'),
    ('<h3 id="evidence">', '<h2 id="evidence">'),
])
def test_content_evidence_hierarchy_and_visibility_changes_need_review(old, new):
    before = ('<h2 id="first">First</h2><p>First answer.</p>'
              '<h2 id="second">Second</h2><p>Keep <span>A</span><span hidden>B</span>. '
              '<a class="citation" href="#code">Source</a></p>'
              '<h3 id="evidence">Evidence</h3><pre id="code">Exact source.</pre>')
    after = before.replace('<h2 id="second">', '<p>New condition.</p><h2 id="second">').replace(old, new)
    updated, stats = reuse(before, after)
    assert 'guide.html#second' in stats['pending']
    assert 'guide.html#second' not in updated['items']


def test_carried_sibling_figure_must_still_be_adjacent():
    before = ('<h2 id="first">First</h2><p>First answer.</p>'
              '<h2 id="second">Second</h2><p>Second answer.</p>'
              '<h2 id="third">Third</h2>' + FIGURE)
    original = ledger(inventory(before))
    original['items']['guide.html#second'].update(
        status='appropriate', figures=['states'], adjacent_item='guide.html#third',
        adjacent_fingerprint=original['items']['guide.html#third']['fingerprint'])
    changed = before.replace('<h2 id="second">', '<p>New condition.</p><h2 id="second">')
    updated, _ = reuse(before, changed, previous_ledger=original)
    assert updated['items']['guide.html#second']['adjacent_fingerprint'] == updated['items']['guide.html#third']['fingerprint']
    separated = changed.replace('<h2 id="third">', '<h2 id="inserted">New sibling</h2><h2 id="third">')
    updated, stats = reuse(before, separated, previous_ledger=original)
    assert 'guide.html#second' not in updated['items']
    assert 'guide.html#second' in stats['pending']


@pytest.mark.parametrize('source_link', ['github', 'gitiles'])
def test_cross_revision_reuse_checks_source_blobs_and_rendered_review_scope(tmp_path, source_link):
    from sdd.config import SiteConfig
    from sdd.source_links import source_link_template
    from sdd.visual_audit import REPORT, inspect_site

    def git(*args):
        return subprocess.check_output(['git', *args], cwd=tmp_path).decode().strip()

    git('init', '-q')
    git('config', 'user.name', 'Fixture')
    git('config', 'user.email', 'fixture@example.test')
    for file in ('stable.cpp', 'changed.cpp', 'extra.cpp'):
        (tmp_path / file).write_bytes(b'original\n')
    git('add', '*.cpp')
    git('commit', '-qm', 'Baseline')
    old = git('rev-parse', 'HEAD')
    for file in ('changed.cpp', 'extra.cpp'):
        (tmp_path / file).write_bytes(b'changed\n')
    git('commit', '-qam', 'Source update')
    new = git('rev-parse', 'HEAD')
    url = 'https://example.test/project'
    settings = SiteConfig(source_url=url, source_link=source_link)
    template = source_link_template(settings)
    options = policy()
    baseline, current = tmp_path / 'baseline', tmp_path / 'current'
    for folder in (baseline, current):
        folder.mkdir()

    def body(commit, figure, explanation, local):
        def citation(file, revision):
            link = template.format(url=url, commit=revision, file=file, line=1)
            return f'<a class="citation" href="{link}"><code>{file}:1</code></a>'

        stable = citation('stable.cpp', commit)
        evidence = html.escape(json.dumps([['stable.cpp:1', stable]]), quote=True)
        local_cite = '<a href="#source-1234567890abcdef"><code>record.txt:1</code></a>'
        local_evidence = html.escape(json.dumps([['record.txt:1', local_cite]]), quote=True)
        return document(f'<h2 id="stable">Stable answer</h2><p data-sdd-evidence="{evidence}">{stable}</p>'
                        f'<h2 id="changed">Changed source</h2><p>{citation("changed.cpp", old)}</p>'
                        '<h2 id="additional">Additional source</h2><p>Same paragraph.</p>'
                        f'<h2 id="prose">Explanation</h2><p>{explanation}</p>'
                        f'<h2 id="figure-item">Picture</h2>{figure}'
                        f'<h2 id="product">Product evidence</h2><p data-sdd-evidence="{local_evidence}">Same statement.</p>'
                        f'<h2 id="evidence">Recorded source</h2><pre id="source-1234567890abcdef">{local}</pre>')

    def write_manifest(folder, files, inputs):
        outputs = {name: hashlib.sha256((folder / name).read_bytes()).hexdigest() for name in files}
        (folder / 'site-manifest.json').write_text(json.dumps(dict(schema=1, build_id=folder.name,
            inputs=inputs, outputs=outputs)), encoding='utf-8')

    (baseline / 'guide.html').write_text(body(old, FIGURE, 'Original.', 'Original record.'), encoding='utf-8')
    (current / 'guide.html').write_text(body(new, FIGURE.replace('ready', 'waiting'), 'New condition.', 'Changed record.'), encoding='utf-8')
    inspected = inspect_site(baseline, options, source_commit=old)
    reviewed = ledger(inspected)
    key = f'git:{old}:extra.cpp#L1-L1'
    reviewed['items']['guide.html#additional'].update(additional_source_windows=[key],
        additional_source_manifest={key: dict(file='extra.cpp', source_commit=old, first_line=1, last_line=1,
            sha256=hashlib.sha256(b'original\n').hexdigest())})
    reviewed['items']['guide.html#stable']['review_record'] = 'original-receipt'
    review_path = tmp_path / 'reviews.json'
    review_path.write_text(json.dumps(reviewed), encoding='utf-8')
    (baseline / REPORT).write_text(json.dumps(apply_reviews(inspected, reviewed)), encoding='utf-8')
    write_manifest(baseline, ['guide.html', REPORT], {'item_visual_reviews': hashlib.sha256(review_path.read_bytes()).hexdigest()})
    write_manifest(current, ['guide.html'], {})

    with pytest.raises(ValueError, match='immutable Git source proof'):
        reuse_published(baseline, current, review_path, options, source_commit=new)
    retained, result = reuse_published(baseline, current, review_path, options, source_commit=new,
                                       source_root=tmp_path, source_settings=settings)
    assert set(retained['items']) == {'guide.html#stable'}
    row = retained['items']['guide.html#stable']
    assert row['review_record'] == 'original-receipt'
    assert row['source_reuse']['previous_commit'] == old and row['source_reuse']['current_commit'] == new
    assert row['fingerprint'] != reviewed['items']['guide.html#stable']['fingerprint']
    assert result['source_revision'] == 1
    assert {'guide.html#changed', 'guide.html#additional', 'guide.html#prose', 'guide.html#figure-item',
            'guide.html#product'} <= set(result['pending'])
    assert result['source_proof']['files'] == [dict(commit=old, path='stable.cpp',
                                                    sha256=hashlib.sha256(b'original\n').hexdigest())]
