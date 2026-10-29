"""Reader-facing evidence compression must preserve provenance and prose."""
import re
from collections import Counter

from sdd.evidence_navigation import compact_evidence, fold_source_details
from sdd.export_site import _render
from sdd.site_localization import DisplayText, display_strings


def test_grouped_disclosures_preserve_all_destinations_and_claim_association():
    source = ('<p>Keep this claim and <code>identifier</code>. '
              '<a class="citation" href="https://example/commit/a#L1"><code>src/a.cpp:1</code></a>, '
              '<a class="citation" href="https://example/commit/a#L8"><code>src/a.cpp:8</code></a></p>'
              '<p>근거 원문: <a href="#source-1111111111111111">src/a.cpp:1</a> · '
              '<a href="#source-8888888888888888">src/a.cpp:8</a></p>')
    result = compact_evidence(source, {'src/a.cpp:1', 'src/a.cpp:8'})
    assert result.startswith('<p>Keep this claim and <code>identifier</code>.</p><details')
    expected = Counter(re.findall('href="([^"]+)"', source))
    expected.update(['#source-1111111111111111', '#source-8888888888888888'])
    assert Counter(re.findall('href="([^"]+)"', result)) == expected
    assert result.index('href="#source-1111111111111111"') < result.index('href="https://example/commit/a#L1"')
    assert '발췌</a>' in result and '전체 소스 <code>L1</code>' in result
    assert result.count('<code>src/a.cpp</code>') == 2  # once in each independent scope
    assert result.count('aria-label="src/a.cpp:1"') == 2
    assert '<summary>문단 근거 <span>2</span>개</summary>' in result
    assert '<summary>절 전체 근거 <span>2</span>개</summary>' in result
    assert ' open' not in result and '<p><details' not in result
    assert compact_evidence(result, {'src/a.cpp:1', 'src/a.cpp:8'}) == result


def test_offline_paragraph_links_to_the_unique_local_excerpt():
    source = ('<p>Claim. <code>a.cpp:1</code></p><p>근거 원문: '
              '<a href="#source-1111111111111111">a.cpp:1</a></p>')
    result = compact_evidence(source, {'a.cpp:1'})
    assert result.count('href="#source-1111111111111111"') == 2
    # Ambiguous excerpts must not silently choose one version.
    source += '<p>근거 원문: <a href="#source-2222222222222222">a.cpp:1</a></p>'
    result = compact_evidence(source, {'a.cpp:1'})
    assert '<span title="a.cpp:1"><code>L1</code></span>' in result


def test_unknown_inline_standalone_and_example_code_remain_visible():
    source = ('<p>Unknown. <code>a.cpp:1</code>, <code>missing.cpp:2</code></p>'
              '<p>Use <code>a.cpp:1</code> to compare the behavior.</p>'
              '<p><code>a.cpp:1</code></p>'
              '<p><code>a.cpp:1</code>, <code>a.cpp:2</code>, <code>a.cpp:3</code></p>'
              '<p><a class="citation" href="https://host/a#L1"><code>a.cpp:1</code></a>, '
              '<a class="citation" href="https://host/a#L2"><code>a.cpp:2</code></a></p>'
              '<pre><p>Example. <code>a.cpp:1</code></p></pre>'
              '<p>근거 원문: <a href="#source-1111111111111111">a.cpp:1</a> explanation</p>')
    assert compact_evidence(source, {'a.cpp:1', 'a.cpp:2', 'a.cpp:3'}) == source
    assert compact_evidence(source, set()) == source


def test_host_citation_keeps_destination_when_local_excerpt_is_ambiguous():
    source = ('<p>Claim. <a class="citation" href="https://host/a#L1"><code>a.cpp:1</code></a></p>'
              '<p>근거 원문: <a href="#source-1111111111111111">a.cpp:1</a> · '
              '<a href="#source-2222222222222222">a.cpp:1</a></p>')
    result = compact_evidence(source, {'a.cpp:1'})
    assert result.count('href="#source-1111111111111111"') == 1
    assert 'href="https://host/a#L1"' in result
    assert '발췌</a>' not in result


def test_renderer_requires_matching_commit_and_keeps_local_anchors(sample_model):
    sample_model.meta['source_commit'] = 'a' * 40
    body = 'Claim. `device/CameraDevice.h:40`\n\n근거 원문: [device/CameraDevice.h:40](#source-1111111111111111)'
    rendered, _, _ = _render(body, 'test.md', set(), sample_model, '', 'a' * 40)
    assert 'evidence-paragraph' in rendered and 'href="#source-1111111111111111"' in rendered
    stale, _, _ = _render(body, 'test.md', set(), sample_model, '', 'b' * 40)
    assert 'evidence-paragraph' not in stale


def test_english_ui_keeps_evidence_identifiers_and_destinations():
    result = compact_evidence('<p>Claim. <code>a.cpp:1</code></p>', {'a.cpp:1'})
    assert display_strings(result) == ['문단 근거 {{1}}개']
    parser = DisplayText(lambda text: text.replace('문단 근거 {{1}}개', 'Paragraph evidence · {{1}}'))
    parser.feed(result)
    translated = ''.join(parser.output)
    assert 'Paragraph evidence · <span>1</span>' in translated
    assert 'title="a.cpp:1"' in translated


def test_source_collection_folds_without_changing_excerpts_or_adjacent_sections():
    from sdd.contract_render import SourceDetails
    sources = SourceDetails()
    sources.records = {
        'source-' + digit * 16: ({}, dict(file=f'src/{digit}.cpp', line=1,
                                        end_line=3, sha256=digit * 64,
                                        text='// Preserve <condition>\nreturn 0;'))
        for digit in ('1', '2')
    }
    review = '\n\n??? note "근거와 검토 정보"\n    사람 검토 전입니다.\n'
    body = '## 설명\n\n설명입니다.\n\n' + sources.render() + review + '\n\n## 다음 절\n\n다음 설명입니다.'
    rendered, toc, _ = _render(body, 'test.md', set(), None, '', '')
    assert '<summary>소스 발췌 <span>2</span>개</summary>' in rendered
    assert '<details class="source-excerpts">' in rendered
    assert '소스-근거' in toc
    assert '</details>\n<details class="note">\n<summary>근거와 검토 정보</summary>' in rendered
    assert rendered.index('근거와 검토 정보') < rendered.index('<h2 id="다음-절">')
    assert 'open' not in rendered
    for digit in ('1', '2'):
        assert rendered.count(f'id="source-{digit * 16}"') == 1
        assert digit * 64 in rendered
    assert rendered.count('Preserve &lt;condition&gt;') == 2
    assert fold_source_details(rendered) == rendered
    assert '소스 발췌 {{1}}개' in display_strings(rendered)
    parser = DisplayText(lambda value: value.replace('소스 발췌 {{1}}개', 'Source excerpts · {{1}}'))
    parser.feed(rendered)
    assert '<summary>Source excerpts · <span>2</span></summary>' in ''.join(parser.output)


def test_ordinary_source_heading_and_example_markup_are_not_folded():
    source = '<h2 id="소스-근거">소스 근거</h2><p>Ordinary explanation.</p>'
    assert fold_source_details(source) == source
    example = '<pre><code>' + source.replace('<', '&lt;').replace('>', '&gt;') + '</code></pre>'
    assert fold_source_details(example) == example
