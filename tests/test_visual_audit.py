"""Behavioral coverage for per-item inventory and preservation boundaries."""
import json

import pytest

from sdd.visual_audit import (apply_reviews, enforce, inspect_site, inventory_page,
                              manuscript_gate, policy)


def document(body, lang='ko'):
    return f'<html lang="{lang}"><article>{body}</article></html>'


FIGURE = ('<!-- sdd:visual:states --><h3 id="figure">State picture</h3>'
          '<pre class="mermaid">flowchart TB\n a["ready"]\n b["done"]\n a --> b</pre>'
          '<details class="note"><summary>Figure evidence</summary><a href="#source-inline">code</a><pre id="source-inline">actual source</pre></details>'
          '<!-- /sdd:visual:states -->')


def report(body, options=None):
    return dict(items=inventory_page(document(body), 'guide.html', options or policy(), source_commit='a'*40),
                policy=options or policy(), errors=[])


def ledger(result, status='omit'):
    return dict(schema=1, items={r['id']: dict(fingerprint=r['fingerprint'], status=status,
        reason='A two-column table directly enumerates the independent values.', question=r['title'],
        source_windows=['item:'+r['id']], unreviewed_scope=[],
        figures=[f['id'] for f in r['figures'] if f['source']]) for r in result['items']})


def test_candidates_are_disjoint_and_never_automatic_acceptance():
    result = report('<h2 id="parent">Parent</h2><p>'+('가'*600)+'</p>'
                    '<h3 id="child">Child</h3><p>first</p><p>second</p><p>third</p>'
                    '<h2 id="short">Return ownership if cancelled</h2><p>Wait for the callback.</p>'
                    '<h2 id="table">Values</h2><table><tr><td>'+('x'*900)+'</td></tr></table>')
    _, parent, child, short, table = result['items']
    assert parent['body_chars'] == 600 and parent['paragraph_count'] == 1
    assert child['paragraph_count'] == 3 and child['parent'] == parent['id']
    assert short['body_chars'] < 600 and 'possible_complexity' in short['candidate_reasons']
    assert table['body_chars'] == 0 and table['table_count'] == 1
    apply_reviews(result, dict(schema=1, items={}))
    assert result['unresolved'] == 5
    with pytest.raises(ValueError, match='incomplete'):
        enforce(result)
    accepted = report('<h2 id="table">Values</h2><table><tr><td>x</td></tr></table>')
    enforce(apply_reviews(accepted, ledger(accepted)))


def test_folded_sources_logs_and_visual_headings_are_not_explanation():
    result = report('<h2 id="one">Question</h2><p>one</p>'+FIGURE+
                    '<p>two</p><details class="source-excerpts"><summary>Source</summary>'
                    '<h3 id="raw">raw</h3><pre>'+('x'*900)+'</pre></details>'
                    '<details><summary>Important condition</summary><p>'+('y'*601)+'</p></details>')
    assert len(result['items']) == 3
    row = result['items'][1]
    assert row['paragraph_count'] == 3 and row['body_chars'] > 600
    assert row['figures'][0]['id'] == 'states'
    assert row['figures'][0]['source'].startswith('flowchart')
    assert row['excluded'][0]['chars'] > 900


@pytest.mark.parametrize('changed', [
    '<h2 id="one">Question</h2><p>new long '+('x'*600)+'</p>',
    '<h2 id="one">Question</h2><h3 id="split">Child</h3><p>old</p>',
    '<h2 id="other">Moved</h2><h3 id="one">Question</h3><p>old</p>',
])
def test_new_long_split_or_moved_item_invalidates_existing_reviews(changed):
    original = report('<h2 id="one">Question</h2><p>old</p>')
    reviews = ledger(original)
    updated = apply_reviews(report(changed), reviews)
    assert updated['unresolved'] > 0
    assert any('changed' in r['reason'] for r in updated['items'])


@pytest.mark.parametrize('replacement', ['', '<!-- sdd:visual:states --><h3>Old</h3><p>Stale omitted</p><!-- /sdd:visual:states -->'])
def test_deleted_or_stale_omitted_figure_cannot_reuse_acceptance(replacement):
    body = '<h2 id="one">Question</h2><p>old</p>'
    original = report(body+FIGURE)
    reviews = ledger(original)
    reviews['items']['guide.html#one'].update(status='appropriate', figures=['states'])
    enforce(apply_reviews(original, reviews))
    updated = report(body+replacement)
    # Even a newly pinned hash cannot approve an absent rendered figure.
    reviews['items']['guide.html#one']['fingerprint'] = updated['items'][1]['fingerprint']
    apply_reviews(updated, reviews)
    assert updated['items'][1]['status'] == 'unreviewed'
    assert 'missing, deleted or stale' in updated['items'][1]['reason']


def test_bilingual_missing_item_and_changed_arrow_are_detected(tmp_path):
    (tmp_path/'en').mkdir()
    ko = '<h2 id="one">Question</h2><p>Ready</p>'+FIGURE
    en = ko.replace('ready', 'Ready in English').replace('done', 'Done in English')
    (tmp_path/'guide.html').write_text(document(ko), encoding='utf-8')
    (tmp_path/'en/guide.html').write_text(document(en, 'en'), encoding='utf-8')
    assert inspect_site(tmp_path, policy())['errors'] == []
    (tmp_path/'en/guide.html').write_text(document(en.replace('a --> b', 'b --> a'), 'en'), encoding='utf-8')
    assert 'figures differ' in inspect_site(tmp_path, policy())['errors'][0]
    (tmp_path/'en/guide.html').write_text(document('<h2 id="two">Other</h2>', 'en'), encoding='utf-8')
    assert any('missing' in e for e in inspect_site(tmp_path, policy())['errors'])


def test_review_needs_scope_and_per_item_reason_and_deferred_cannot_pass():
    options = policy()
    options['deferred_pages'] = {'guide.html': 'PR #231 owns this page; integration pending'}
    result = report('<h2 id="one">One</h2><p>text</p>', options)
    records = ledger(result)
    records['items'][result['items'][0]['id']]['reason'] = ''
    apply_reviews(result, records)
    assert result['unresolved'] == len(result['items'])
    assert 'Another session' in result['items'][1]['reason']


def test_language_threshold_adjustment_needs_reason(tmp_cfg):
    tmp_cfg.raw['visual_audit'] = dict(thresholds={'en': dict(chars=900)})
    with pytest.raises(ValueError, match='rationale'):
        policy(tmp_cfg)
    tmp_cfg.raw['visual_audit']['thresholds']['en']['rationale'] = 'Same bilingual question: KO 550 chars; EN 920 chars. Inspect both.'
    options = policy(tmp_cfg)
    row = inventory_page(document('<h2 id="one">One</h2><p>'+('x'*800)+'</p>', 'en'), 'en/guide.html', options)[1]
    assert 'long_explanation' not in row['candidate_reasons']
    assert row['status'] == 'unreviewed'


def test_failed_publication_preserves_every_previous_owned_byte(tmp_cfg):
    from sdd.site_build import build_site
    tmp_cfg.sdd_dir.mkdir(parents=True)
    def render(cfg, stage, mermaid):
        (stage/'guide.html').write_text(document('<h2 id="one">One</h2><p>text</p>'), encoding='utf-8')
    destination = tmp_cfg.build_dir/'site'
    build_site(tmp_cfg, destination, render, None)
    before = {p.relative_to(destination): p.read_bytes() for p in destination.rglob('*') if p.is_file()}
    tmp_cfg.raw['visual_audit'] = dict(enabled=True, reviews='reviews.json')
    (tmp_cfg.root/'reviews.json').write_text(json.dumps(dict(schema=1, items={})), encoding='utf-8')
    with pytest.raises(ValueError, match='incomplete'):
        build_site(tmp_cfg, destination, render, None)
    assert {p.relative_to(destination): p.read_bytes() for p in destination.rglob('*') if p.is_file()} == before


def test_manuscript_gate_requires_separate_draft_reviews(tmp_cfg, sample_model):
    tmp_cfg.raw['visual_audit'] = dict(enabled=True, reviews='reviews.json')
    (tmp_cfg.root/'reviews.json').write_text(json.dumps(dict(schema=1, items={}, manuscripts={})), encoding='utf-8')
    text = '---\nsource_commit: abc123\n---\n## Question\n\nIf cancelled, return ownership after completion.\n'
    with pytest.raises(ValueError, match='incomplete'):
        manuscript_gate(tmp_cfg, sample_model, tmp_cfg.sdd_dir/'guide.md', text)
    with pytest.raises(ValueError, match='commits differ'):
        manuscript_gate(tmp_cfg, sample_model, tmp_cfg.sdd_dir/'guide.md', text.replace('abc123', 'different'))


def test_source_window_change_invalidates_omit_even_without_body_change():
    source = '<h2 id="one">One</h2><p>text</p><details class="source-excerpts"><pre>original</pre></details>'
    original = report(source)
    updated = report(source.replace('original', 'changed'))
    apply_reviews(updated, ledger(original))
    assert updated['items'][1]['status'] == 'unreviewed'


def test_generation_rolls_back_earlier_pages_if_later_item_fails(tmp_cfg, sample_model, monkeypatch):
    from sdd.generate import Generator
    from sdd.llm import Agent
    import sdd.visual_audit as audit
    tmp_cfg.sdd_dir.mkdir(parents=True)
    first, second = tmp_cfg.sdd_dir/'one.md', tmp_cfg.sdd_dir/'two.md'
    first.write_bytes(b'original one')
    second.write_bytes(b'original two')
    tmp_cfg.raw['visual_audit'] = dict(enabled=True)
    def gate(cfg, model, path, text):
        if path == second:
            raise ValueError('second item incomplete')
    monkeypatch.setattr(audit, 'manuscript_gate', gate)
    generator = Generator(tmp_cfg, sample_model, Agent(tmp_cfg.agent))
    def run(*args):
        generator._write(first, 'new one')
        generator._write(second, 'new two')
    monkeypatch.setattr(generator, '_run', run)
    with pytest.raises(ValueError, match='second item'):
        generator.run()
    assert first.read_bytes() == b'original one' and second.read_bytes() == b'original two'


def test_accepted_report_is_built_and_verified_with_site(tmp_cfg):
    from sdd.site_build import build_site, verify_site
    tmp_cfg.sdd_dir.mkdir(parents=True)
    tmp_cfg.raw['visual_audit'] = dict(enabled=True, reviews='reviews.json')
    body = document('<h2 id="one">Values</h2><table><tr><td>x</td></tr></table>')
    rows = inventory_page(body, 'guide.html', policy(tmp_cfg))
    records = ledger(dict(items=rows))
    (tmp_cfg.root/'reviews.json').write_text(json.dumps(records), encoding='utf-8')
    def render(cfg, stage, mermaid):
        (stage/'guide.html').write_text(body, encoding='utf-8')
    out = build_site(tmp_cfg, tmp_cfg.build_dir/'site', render, None)
    assert verify_site(out)['html_pages'] == 1
    recorded = json.loads((out/'item-visual-audit.json').read_bytes())
    assert recorded['unresolved'] == 0 and recorded['human_review'] == 'pending'


def test_unknown_review_window_cannot_approve():
    result = report('<h2 id="one">One</h2><p>text</p>')
    records = ledger(result)
    records['items']['guide.html#one']['source_windows'] = ['nonexistent.html#fake']
    apply_reviews(result, records)
    assert result['items'][1]['status'] == 'unreviewed'


def test_parent_title_and_ancestry_changes_invalidate_child():
    original = report('<h2 id="parent">Old context</h2><h3 id="child">Child</h3><p>text</p>')
    changed = report('<h2 id="parent">New context</h2><h3 id="child">Child</h3><p>text</p>')
    apply_reviews(changed, ledger(original))
    assert changed['items'][2]['status'] == 'unreviewed'


def test_cross_file_window_content_is_bound_to_item(tmp_path):
    guide = document('<h2 id="one">Question</h2><details class="evidence-links"><a href="source.html#L1">source</a></details>')
    (tmp_path/'guide.html').write_text(guide, encoding='utf-8')
    (tmp_path/'source.html').write_text(document('<pre id="L1">original</pre>'), encoding='utf-8')
    original = inspect_site(tmp_path, policy())
    records = ledger(original)
    records['items']['guide.html#one']['source_windows'] = ['source.html#L1']
    enforce(apply_reviews(original, records))
    (tmp_path/'source.html').write_text(document('<pre id="L1">changed</pre>'), encoding='utf-8')
    updated = apply_reviews(inspect_site(tmp_path, policy()), records)
    assert next(r for r in updated['items'] if r['id']=='guide.html#one')['status'] == 'unreviewed'


def test_disabled_audit_does_not_require_ledger_file(tmp_cfg):
    from sdd.site_build import build_site
    tmp_cfg.sdd_dir.mkdir(parents=True)
    tmp_cfg.raw['visual_audit'] = dict(enabled=False, reviews='absent.json')
    def render(cfg, stage, mermaid):
        (stage/'guide.html').write_text(document('<p>text</p>'), encoding='utf-8')
    out = build_site(tmp_cfg, tmp_cfg.build_dir/'site', render, None)
    assert 'item_visual_reviews' not in json.loads((out/'site-manifest.json').read_bytes())['inputs']


@pytest.mark.parametrize('markers', [
    '<!-- sdd:visual:one -->',
    '<!-- /sdd:visual:one -->',
    '<!-- sdd:visual:one --><!-- /sdd:visual:two -->',
    '<!-- sdd:visual:one --><!-- sdd:visual:two --><!-- /sdd:visual:two --><!-- /sdd:visual:one -->',
])
def test_malformed_visual_markers_cannot_hide_following_items(markers):
    with pytest.raises(ValueError, match='visualization marker'):
        report(markers+'<h2 id="hidden">Must not escape review</h2><p>'+('x'*601)+'</p>')


@pytest.mark.parametrize('fragment', ['L999999', 'L2-L1', 'L1-L3'])
def test_nonexistent_source_line_window_is_rejected(tmp_path, fragment):
    (tmp_path/'guide.html').write_text(document('<h2 id="one">One</h2><details class="evidence-links"><a href="source.cpp#'+fragment+'">source</a></details>'), encoding='utf-8')
    (tmp_path/'source.cpp').write_text('line one\nline two\n', encoding='utf-8')
    with pytest.raises(ValueError, match='line range'):
        inspect_site(tmp_path, policy())


def test_visual_marker_cannot_swallow_an_ordinary_section():
    malicious = FIGURE.replace('<!-- /sdd:visual:states -->', '<h2 id="hidden">Hidden question</h2><p>explanation</p><!-- /sdd:visual:states -->')
    with pytest.raises(ValueError, match='Ordinary section'):
        report('<h2 id="one">One</h2>'+malicious)


def test_caption_and_plain_container_text_are_fingerprinted():
    original = report('<h2 id="one">One</h2>'+FIGURE+'<div>direct explanation</div><blockquote>more</blockquote>')
    changed = report('<h2 id="one">One</h2>'+FIGURE.replace('State picture', 'Different meaning')+'<div>changed explanation</div><blockquote>more</blockquote>')
    assert 'direct explanation' in original['items'][1]['body']
    assert 'more' in original['items'][1]['body']
    assert original['items'][1]['figures'][0]['sha256'] != changed['items'][1]['figures'][0]['sha256']
    assert original['items'][1]['fingerprint'] != changed['items'][1]['fingerprint']


def test_first_heading_inside_marker_is_still_an_inventory_item():
    result = report('<!-- sdd:visual:one --><h3 id="ordinary">Independent question</h3><p>'+('x'*601)+'</p><pre class="mermaid">flowchart TB\n a --> b</pre><!-- /sdd:visual:one -->')
    row = next(r for r in result['items'] if r['anchor']=='ordinary')
    assert row['body_chars'] == 601 and row['paragraph_count'] == 1
    assert row['status'] == 'unreviewed'


@pytest.mark.parametrize('body', ['<!-- sdd:visual:Figure -->', '<!-- sdd:visual: -->', '<!-- sdd:class-diagramBAD -->'])
def test_malformed_marker_prefix_fails_closed(body):
    with pytest.raises(ValueError, match='Malformed visualization marker'):
        report(body)


def test_visual_details_cannot_hide_section_and_link_changes_are_bound():
    source = '<h2 id="one">One</h2>'+FIGURE
    with pytest.raises(ValueError, match='Ordinary section'):
        report(source.replace('<summary>Figure evidence</summary>', '<summary>Figure evidence</summary><h3>hidden</h3>'))
    original, changed = report(source), report(source.replace('#source-inline','other.html#L2'))
    assert original['items'][1]['figures'][0]['sha256'] != changed['items'][1]['figures'][0]['sha256']


def test_same_page_heading_window_includes_section_body():
    source = '<h2 id="one">One</h2><details class="evidence-links"><a href="#two">source</a></details><h2 id="two">Two</h2><p>original</p><h3 id="sub">Sub</h3><p>nested</p>'
    original = report(source)
    changed = report(source.replace('original', 'changed'))
    assert original['items'][1]['source_window_hashes']['guide.html#two'] != changed['items'][1]['source_window_hashes']['guide.html#two']


def test_fragmentless_local_evidence_is_fingerprinted(tmp_path):
    source = '<h2 id="one">One</h2><details class="evidence-links"><a href="source.txt">source</a></details>'
    (tmp_path/'guide.html').write_text(document(source), encoding='utf-8')
    (tmp_path/'source.txt').write_text('original', encoding='utf-8')
    original = inspect_site(tmp_path, policy())
    records = ledger(original)
    records['items']['guide.html#one']['source_windows'] = ['source.txt']
    enforce(apply_reviews(original, records))
    (tmp_path/'source.txt').write_text('changed', encoding='utf-8')
    updated = apply_reviews(inspect_site(tmp_path, policy()), records)
    assert updated['items'][1]['status'] == 'unreviewed'


def test_unresolved_figure_evidence_cannot_be_approved_with_item_window():
    result = report('<h2 id="one">One</h2>'+FIGURE.replace('#source-inline', 'missing.html#L1'))
    records = ledger(result)
    records['items']['guide.html#one'].update(status='appropriate', figures=['states'])
    apply_reviews(result, records)
    assert result['items'][1]['status'] == 'unreviewed'
    assert 'unresolved' in result['items'][1]['reason']


def test_heading_source_link_attributes_and_asset_bytes_are_bound(tmp_path):
    guide = document('<h2 id="one">One</h2><details class="evidence-links"><a href="#two">source</a></details><h2 id="two">Two</h2><p><a href="target.txt">link</a><img src="image.svg"></p>')
    (tmp_path/'guide.html').write_text(guide, encoding='utf-8')
    (tmp_path/'target.txt').write_text('target', encoding='utf-8')
    (tmp_path/'image.svg').write_text('<svg>first</svg>', encoding='utf-8')
    original = inspect_site(tmp_path, policy())
    before = original['items'][1]['source_window_hashes']['guide.html#two']
    (tmp_path/'image.svg').write_text('<svg>changed</svg>', encoding='utf-8')
    changed = inspect_site(tmp_path, policy())
    assert before != changed['items'][1]['source_window_hashes']['guide.html#two']


def test_draft_figure_download_is_not_unresolved_hal_evidence(tmp_cfg, sample_model):
    from sdd.site_markdown import _render
    tmp_cfg.raw['visual_audit'] = dict(enabled=True, reviews='reviews.json')
    body = '## Question\n\ntext\n\n'+FIGURE.replace('<!-- /sdd:visual:states -->', '<p><a href="guide.states.mmd">Mermaid original</a></p><!-- /sdd:visual:states -->')
    rendered, _, _ = _render(body, 'guide.md', {'guide.md'}, sample_model, '', 'abc123')
    rows = inventory_page(document(rendered), 'guide.html', policy(tmp_cfg), source_commit='abc123', root=tmp_cfg.sdd_dir, draft=True)
    records = ledger(dict(items=rows))
    records['items']['guide.html#question'].update(status='appropriate', figures=['states'])
    (tmp_cfg.root/'reviews.json').write_text(json.dumps(dict(schema=1, items={}, manuscripts=records['items'])), encoding='utf-8')
    manuscript_gate(tmp_cfg, sample_model, tmp_cfg.sdd_dir/'guide.md', '---\nsource_commit: abc123\n---\n'+body)
    assert not (tmp_cfg.sdd_dir/'guide.states.mmd').exists()


def test_folded_source_attributes_and_local_assets_invalidate_review(tmp_path):
    text = document('<h2 id="one">One</h2><details class="evidence-links"><a href="#source-code">source</a></details><details class="source-excerpts"><pre id="source-code">code</pre><img src="image.svg"></details>')
    (tmp_path/'guide.html').write_text(text, encoding='utf-8')
    (tmp_path/'image.svg').write_text('<svg>old</svg>', encoding='utf-8')
    original = inspect_site(tmp_path, policy())
    (tmp_path/'image.svg').write_text('<svg>changed</svg>', encoding='utf-8')
    changed = inspect_site(tmp_path, policy())
    assert original['items'][1]['source_window_hashes'] != changed['items'][1]['source_window_hashes']


def test_text_position_inside_source_markup_is_bound():
    prefix = '<h2 id="one">One</h2><details class="evidence-links"><a href="#source-code">source</a></details><details class="source-excerpts" id="source-code">'
    first = report(prefix+'<a href="target">linked</a> outside</details>')
    second = report(prefix+'<a href="target">linked outside</a></details>')
    assert first['items'][1]['source_window_hashes'] != second['items'][1]['source_window_hashes']


def test_unrelated_external_target_cannot_borrow_any_local_proof_link():
    local = '<details class="source-excerpts" id="source-code"><pre>actual code</pre><a href="https://source.example/right">full source</a></details>'
    picture = FIGURE.replace('<a href="#source-inline">code</a>', '<table><tr><td><a href="#source-code">excerpt</a><a href="https://source.example/wrong">unrelated target</a></td></tr></table>')
    result = report('<h2 id="one">One</h2>'+picture+local)
    records = ledger(result)
    records['items']['guide.html#one'].update(status='appropriate', figures=['states'])
    apply_reviews(result, records)
    assert result['items'][1]['status'] == 'unreviewed'
    assert 'unresolved' in result['items'][1]['reason']
    matched = report('<h2 id="one">One</h2>'+picture.replace('href="https://source.example/wrong"','href="https://source.example/right" data-sdd-convenience="true"')+local)
    records = ledger(matched)
    records['items']['guide.html#one'].update(status='appropriate', figures=['states'])
    enforce(apply_reviews(matched, records))
    binding = matched['items'][1]['figures'][0]['convenience_links'][0]
    assert binding['local_window'] == 'guide.html#source-code' and binding['external_fetched'] is False


def test_responsive_image_candidates_are_bound(tmp_path):
    source = document('<h2 id="one">One</h2><details class="evidence-links"><a href="#source-code">source</a></details><details class="source-excerpts" id="source-code"><img srcset="small.svg 1x, large.svg 2x"></details>')
    (tmp_path/'guide.html').write_text(source, encoding='utf-8')
    for name in ['small.svg', 'large.svg']:
        (tmp_path/name).write_text('<svg>old</svg>', encoding='utf-8')
    original = inspect_site(tmp_path, policy())
    (tmp_path/'large.svg').write_text('<svg>changed</svg>', encoding='utf-8')
    changed = inspect_site(tmp_path, policy())
    assert original['items'][1]['source_window_hashes'] != changed['items'][1]['source_window_hashes']


def test_published_mermaid_download_must_match_inline_source(tmp_path):
    source = document('<h2 id="one">One</h2>'+FIGURE.replace('<!-- /sdd:visual:states -->', '<p><a href="guide.states.mmd">Mermaid</a></p><!-- /sdd:visual:states -->'))
    (tmp_path/'guide.html').write_text(source, encoding='utf-8')
    with pytest.raises(ValueError, match='download missing'):
        inspect_site(tmp_path, policy())
    (tmp_path/'guide.states.mmd').write_text('wrong diagram', encoding='utf-8')
    with pytest.raises(ValueError, match='differs'):
        inspect_site(tmp_path, policy())
    (tmp_path/'guide.states.mmd').write_text('flowchart TB\n a["ready"]\n b["done"]\n a --> b\n', encoding='utf-8', newline='\n')
    assert inspect_site(tmp_path, policy())['items'][1]['figures'][0]['download_bindings']
    with (tmp_path/'guide.states.mmd').open('a', encoding='utf-8') as stream:
        stream.write('\n')
    with pytest.raises(ValueError, match='differs'):
        inspect_site(tmp_path, policy())


def test_svg_image_asset_is_bound(tmp_path):
    source = document('<h2 id="one">One</h2><details class="evidence-links"><a href="#source-code">source</a></details><details class="source-excerpts" id="source-code"><svg><image href="image.svg"/></svg></details>')
    (tmp_path/'guide.html').write_text(source, encoding='utf-8')
    (tmp_path/'image.svg').write_text('<svg>old</svg>', encoding='utf-8')
    original = inspect_site(tmp_path, policy())
    (tmp_path/'image.svg').write_text('<svg>changed</svg>', encoding='utf-8')
    changed = inspect_site(tmp_path, policy())
    assert original['items'][1]['source_window_hashes'] != changed['items'][1]['source_window_hashes']


def test_writing_policy_change_requires_new_item_review(tmp_cfg):
    original = report('<h2 id="one">One</h2><p>text</p>', policy(tmp_cfg))
    records = ledger(original)
    guide = tmp_cfg.style_dir/'README.md'
    guide.write_text(guide.read_text(encoding='utf-8')+'\nNew visualization review policy.\n', encoding='utf-8')
    changed = apply_reviews(report('<h2 id="one">One</h2><p>text</p>', policy(tmp_cfg)), records)
    assert changed['unresolved'] == len(changed['items'])
