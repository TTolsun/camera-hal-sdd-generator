"""Section evidence preserves provenance without per-paragraph controls."""
import html
import json
import re

from sdd.evidence_navigation import compact_evidence
from sdd.export_site import _render
from sdd.site_localization import DisplayText, display_strings


def test_section_union_and_noninteractive_paragraph_mapping():
    refs = [('a.cpp:1', '<a class="citation" href="https://host/commit/a#L1"><code>a.cpp:1</code></a>'),
            ('a.cpp:8', '<a class="citation" href="https://host/commit/a#L8"><code>a.cpp:8</code></a>')]
    source = ('<h2>First</h2><p>Keep this claim and <code>identifier</code>. '
              + ', '.join(element for _, element in refs) + '</p>'
              '<p>근거 원문: <a href="#source-1111111111111111">a.cpp:1</a></p>'
              '<h2>Next</h2><p>Other prose.</p>')
    result = compact_evidence(source, {'a.cpp:1', 'a.cpp:8'})
    assert '문단 근거' not in result and 'evidence-paragraph' not in result
    mapping = json.loads(html.unescape(re.search(r'data-sdd-evidence="([^"]+)"', result)[1]))
    assert mapping == [list(ref) for ref in refs]
    assert '>Keep this claim and <code>identifier</code>.</p>' in result
    assert result.count('evidence-section') == 1
    assert result.index('evidence-section') < result.index('<h2>Next')
    assert '<summary>절 전체 근거 <span>2</span>개</summary>' in result
    for destination in ['https://host/commit/a#L1', 'https://host/commit/a#L8', '#source-1111111111111111']:
        assert f'href="{destination}"' in result
    assert '발췌</a>' in result and '전체 소스 <code>L1</code>' in result
    assert ' open' not in result and '<p><details' not in result
    assert compact_evidence(result, {'a.cpp:1', 'a.cpp:8'}) == result


def test_offline_and_ambiguous_local_destinations_survive():
    source = ('<p>Claim. <code>a.cpp:1</code></p><p>근거 원문: '
              '<a href="#source-1111111111111111">a.cpp:1</a></p>')
    result = compact_evidence(source, {'a.cpp:1'})
    assert result.count('href="#source-1111111111111111"') == 1
    source += '<p>근거 원문: <a href="#source-2222222222222222">a.cpp:1</a></p>'
    result = compact_evidence(source, {'a.cpp:1'})
    assert 'href="#source-1111111111111111"' in result
    assert 'href="#source-2222222222222222"' in result
    assert '발췌</a>' not in result


def test_unknown_inline_standalone_and_example_code_remain_visible():
    source = ('<p>Unknown. <code>a.cpp:1</code>, <code>missing.cpp:2</code></p>'
              '<p>Use <code>a.cpp:1</code> to compare the behavior.</p>'
              '<p><code>a.cpp:1</code></p><p><code>a.cpp:1</code>, <code>a.cpp:2</code></p>'
              '<pre><h2>Example</h2><p>Example. <code>a.cpp:1</code></p></pre>'
              '<p>근거 원문: <a href="#source-1111111111111111">a.cpp:1</a> explanation</p>')
    assert compact_evidence(source, {'a.cpp:1', 'a.cpp:2'}) == source
    assert compact_evidence(source, set()) == source


def test_renderer_requires_matching_commit_and_keeps_local_anchors(sample_model):
    sample_model.meta['source_commit'] = 'a' * 40
    body = 'Claim. `device/CameraDevice.h:40`\n\n근거 원문: [device/CameraDevice.h:40](#source-1111111111111111)'
    rendered, _, _ = _render(body, 'test.md', set(), sample_model, '', 'a' * 40)
    assert 'data-sdd-evidence' in rendered and 'href="#source-1111111111111111"' in rendered
    stale, _, _ = _render(body, 'test.md', set(), sample_model, '', 'b' * 40)
    assert 'data-sdd-evidence' not in stale


def test_english_ui_preserves_mapping_without_extra_search_text():
    result = compact_evidence('<p>Claim. <code>a.cpp:1</code></p>', {'a.cpp:1'})
    assert display_strings(result) == ['절 전체 근거 {{1}}개']
    parser = DisplayText(lambda text: text.replace('절 전체 근거 {{1}}개', 'Section evidence · {{1}}'))
    parser.feed(result)
    translated = ''.join(parser.output)
    assert 'Section evidence · <span>1</span>' in translated
    assert 'data-sdd-evidence=' in translated and 'title="a.cpp:1"' in translated


def test_each_heading_gets_only_its_own_evidence_and_duplicate_claims_do_not_grow_index():
    source = '<h2>A</h2><p>One. <code>a.cpp:1</code></p><p>Two. <code>a.cpp:1</code></p><h2>B</h2><p>Three. <code>b.cpp:2</code></p>'
    result = compact_evidence(source, {'a.cpp:1', 'b.cpp:2'})
    first, second = result.split('<h2>B</h2>')
    assert first.count('title="a.cpp:1"') == 1 and 'b.cpp' not in first
    assert second.count('title="b.cpp:2"') == 1 and 'a.cpp' not in second
