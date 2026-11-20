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


_OLD_LOCATION = '<a class="citation" href="https://example.test/camera.cpp#L10"><code>{cite}</code></a>에서 시작하는 발췌입니다. 종료 줄은 {end}이며, 아래 원문을 설명과 대조할 수 있습니다.'
_NEW_LOCATION = '발췌 범위: <a class="citation" href="https://example.test/camera.cpp#L10"><code>{cite}</code></a> ~ <code>{end}</code>'
_OLD_EN = 'This excerpt starts at <a class="citation" href="https://example.test/camera.cpp#L10"><code>{cite}</code></a> and ends at line {end}.'
_NEW_EN = 'Excerpt range: <a class="citation" href="https://example.test/camera.cpp#L10"><code>{cite}</code></a> to <code>{end}</code>'
_OLD_EN_SCOPE = 'This is a design interpretation linked to the source.'
_NEW_EN_SCOPE = ('Source-linked interpretation · automatic link check only'
                 ' · meaning and device execution not yet verified')


def _catalog(*, legacy=True):
    from sdd.reading_cleanup import VISUAL_SCOPE_SENTENCE
    strings = {'발췌 범위: {{1}} ~ {{3}}': 'Excerpt range: {{1}} to {{3}}'}
    if legacy:
        strings['{{0}}에서 시작하는 발췌입니다. 종료 줄은 12이며, 아래 원문을 설명과 대조할 수 있습니다.'] = \
            'This excerpt starts at {{0}} and ends at line 12.'
        strings[VISUAL_SCOPE_SENTENCE] = _OLD_EN_SCOPE
    return dict(schema=1, strings=strings)


def _note_page(location_line, scope_line, *, source='void stop();', question='누가 요청을 완료합니까?',
               cite='camera.cpp:10', end='12', title='소스 근거', extra=''):
    return ('<h2 id="stop">정지</h2><p>요청을 취소합니다. <a class="citation" href="#source-1">camera.cpp:10</a></p>'
            '<h2 id="figure-item">그림</h2>' + FIGURE.replace(
                '<details class="note"><summary>Figure evidence</summary>',
                f'<details class="note"><summary>그림 근거와 확인 범위</summary><p>{question}</p><p>{scope_line}</p>')
            + '<h2 id="evidence">소스 근거</h2><p><a id="source-1"></a></p>'
            f'<details class="note"><summary>{title}: camera.cpp:10</summary>'
            f'<p>{location_line.format(cite=cite, end=end)}{extra}</p><p>SHA-256: <code>{"a" * 64}</code></p>'
            f'<pre id="source-excerpt">{source}</pre></details>')


def _items(body, page='guide.html', **kwargs):
    options = policy()
    lang = 'en' if page.startswith('en/') else 'ko'
    return dict(items=inventory_page(document(body, lang), page, options, source_commit='a' * 40, **kwargs),
                policy=options, errors=[])


def _presentation_reuse(before, after, *, page='guide.html', catalogs=(None, None)):
    from sdd.reading_cleanup import VISUAL_SCOPE_LABEL, VISUAL_SCOPE_SENTENCE
    from sdd.visual_review_reuse import presentation_normalizer
    old = before.replace('{SCOPE}', VISUAL_SCOPE_SENTENCE)
    new = after.replace('{SCOPE}', VISUAL_SCOPE_LABEL)
    original = _items(old, page)
    return carry_reviews(ledger(original), original, _items(new, page), _items(old, page, section_relative=True),
                         _items(new, page, section_relative=True), baseline_build='old-build', stable_pages={page},
                         presentation=(_items(old, page, comparison_transform=presentation_normalizer(catalogs[0])),
                                       _items(new, page, comparison_transform=presentation_normalizer(catalogs[1]))))


def test_generator_note_label_changes_carry_reviews_with_presentation_provenance():
    from sdd.reading_cleanup import VISUAL_SCOPE_LABEL
    updated, stats = _presentation_reuse(_note_page(_OLD_LOCATION, '{SCOPE}'), _note_page(_NEW_LOCATION, '{SCOPE}'))
    assert stats['pending'] == [] and stats['presentation_only'] >= 1
    carried = [row for row in updated['items'].values() if 'presentation_reuse' in row]
    assert carried and all(row['presentation_reuse']['normalization'] == 'generator-note-labels-v3'
                           and row['presentation_reuse']['baseline_build_id'] == 'old-build' for row in carried)
    # Published audit rows keep the provenance: apply_reviews copies it.
    applied = apply_reviews(_items(_note_page(_NEW_LOCATION, VISUAL_SCOPE_LABEL)), updated)
    assert any('presentation_reuse' in row for row in applied['items'])


@pytest.mark.parametrize(('field', 'value'), [
    ('source', 'void start();'),
    ('question', '누가 요청을 시작합니까?'),
    ('cite', 'camera.cpp:11'),
    ('end', '13'),
    ('extra', ' 이 범위는 정지 경로만 포함합니다.'),
])
def test_note_normalization_never_hides_excerpt_figure_range_or_prose_changes(field, value):
    _, stats = _presentation_reuse(_note_page(_OLD_LOCATION, '{SCOPE}'),
                                   _note_page(_NEW_LOCATION, '{SCOPE}', **{field: value}))
    assert stats['pending'], field


def test_unknown_korean_scope_wording_is_not_normalized():
    _, stats = _presentation_reuse(_note_page(_OLD_LOCATION, '{SCOPE}'),
                                   _note_page(_OLD_LOCATION, '사람이 의미를 승인했습니다.'))
    assert stats['pending']


def test_english_lines_are_normalized_only_when_they_match_the_build_catalog():
    before = _note_page(_OLD_EN, _OLD_EN_SCOPE, title='Source evidence')
    after = _note_page(_NEW_EN, _NEW_EN_SCOPE, title='Source evidence')
    catalogs = (_catalog(), _catalog(legacy=False))
    _, stats = _presentation_reuse(before, after, page='en/guide.html', catalogs=catalogs)
    assert stats['pending'] == [] and stats['presentation_only'] >= 1
    # Without the baseline catalog nothing proves the old English was generated.
    _, stats = _presentation_reuse(before, after, page='en/guide.html', catalogs=(None, catalogs[1]))
    assert stats['pending']
    # Edited English scope wording is not a catalog value, so it stays in the fingerprint.
    edited = _note_page(_NEW_EN, 'Reviewed by a human and approved.', title='Source evidence')
    _, stats = _presentation_reuse(before, edited, page='en/guide.html', catalogs=catalogs)
    assert stats['pending']


def test_product_note_title_wording_is_a_label_change():
    before = _note_page(_OLD_EN, _OLD_EN_SCOPE, title='Product material')
    after = _note_page(_NEW_EN, _NEW_EN_SCOPE, title='Product evidence')
    _, stats = _presentation_reuse(before, after, page='en/guide.html', catalogs=(_catalog(), _catalog(legacy=False)))
    assert stats['pending'] == []


def test_method_comes_from_this_run_not_from_ledger_provenance():
    from sdd.reading_cleanup import VISUAL_SCOPE_LABEL
    carried, _ = _presentation_reuse(_note_page(_OLD_LOCATION, '{SCOPE}'), _note_page(_NEW_LOCATION, '{SCOPE}'))
    report = _items(_note_page(_NEW_LOCATION, VISUAL_SCOPE_LABEL))
    # Reusing the carried ledger on an identical site is exact, not presentation_only.
    _, stats = carry_reviews(carried, report, report, report, report, baseline_build='next-build',
                             stable_pages={'guide.html'}, presentation=(report, report))
    assert stats['presentation_only'] == 0 and stats['exact'] == len(carried['items'])


def test_reuse_published_wires_presentation_normalization(tmp_path):
    from sdd.reading_cleanup import VISUAL_SCOPE_LABEL, VISUAL_SCOPE_SENTENCE
    from sdd.visual_audit import REPORT, inspect_site

    options = policy()
    baseline, current = tmp_path / 'baseline', tmp_path / 'current'
    for folder in (baseline, current):
        folder.mkdir()
    (baseline / 'guide.html').write_text(document(_note_page(_OLD_LOCATION, VISUAL_SCOPE_SENTENCE)), encoding='utf-8')
    (current / 'guide.html').write_text(document(_note_page(_NEW_LOCATION, VISUAL_SCOPE_LABEL)), encoding='utf-8')

    def write_manifest(folder, files, inputs):
        outputs = {name: hashlib.sha256((folder / name).read_bytes()).hexdigest() for name in files}
        (folder / 'site-manifest.json').write_text(json.dumps(dict(schema=1, build_id=folder.name,
            inputs=inputs, outputs=outputs)), encoding='utf-8')

    inspected = inspect_site(baseline, options, source_commit='a' * 40)
    reviewed = ledger(inspected)
    review_path = tmp_path / 'reviews.json'
    review_path.write_text(json.dumps(reviewed), encoding='utf-8')
    (baseline / REPORT).write_text(json.dumps(apply_reviews(inspected, reviewed)), encoding='utf-8')
    write_manifest(baseline, ['guide.html', REPORT],
                   {'item_visual_reviews': hashlib.sha256(review_path.read_bytes()).hexdigest()})
    write_manifest(current, ['guide.html'], {})
    retained, result = reuse_published(baseline, current, review_path, options, source_commit='a' * 40)
    assert result['pending'] == [] and result['presentation_only'] >= 1
    assert all('presentation_reuse' in row or row['fingerprint'] == reviewed['items'][key]['fingerprint']
               for key, row in retained['items'].items())
    # A catalog other than the one the site was built with is rejected.
    catalog = tmp_path / 'english.json'
    catalog.write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='English catalog does not match'):
        reuse_published(baseline, current, review_path, options, source_commit='a' * 40, baseline_catalog=catalog)
