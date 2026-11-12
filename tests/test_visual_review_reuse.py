import pytest

from sdd.visual_audit import apply_reviews, inventory_page, policy
from sdd.visual_review_reuse import carry_reviews
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
