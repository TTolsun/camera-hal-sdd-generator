"""Section evidence preserves provenance without per-paragraph controls."""
import html
import json
import re

from sdd.evidence_navigation import compact_evidence, fold_source_details
from sdd.export_site import _render
from sdd.site_localization import DisplayText, display_strings


def test_removed_route_table_preserves_old_fragments_and_unrelated_content():
    body = ('| **지금 확인할 내용** | **이동할 절** |\n|---|---|\n'
            '| <a id="old-route"></a>중복 안내입니다. | [요청 문서](request.md#lifetime) |\n\n'
            '## 본문\n\n본문을 유지합니다.\n\n'
            '| 상태 | 의미 |\n|---|---|\n| 완료 | 재사용 가능 |\n\n'
            '| 시작할 문서 | 이유 |\n|---|---|\n| [개요](overview.md) | 처음 읽습니다. |')
    rendered, _, _ = _render(body, 'test.md', {'test.md', 'request.md', 'overview.md'}, None, '', '')
    assert '지금 확인할 내용' not in rendered and '중복 안내입니다.' not in rendered
    assert '<div class="previous-route" id="old-route">' in rendered
    assert '<a href="request.html#lifetime">요청 문서</a>' in rendered
    assert '<h2 id="본문">본문</h2>' in rendered and '본문을 유지합니다.' in rendered
    assert '재사용 가능' in rendered and '시작할 문서' in rendered


def test_empty_route_table_is_not_published():
    rendered, _, _ = _render('| 지금 확인할 내용 | 이동할 절 |\n|---|---|', 'a.md', set(), None, '', '')
    assert '<table' not in rendered and '지금 확인할 내용' not in rendered


def test_custom_route_cell_content_and_fragments_are_not_discarded():
    for row in ('| [추가 안내](other.md) | [본문](#body) |',
                '| `코드 예제` | [본문](#body) |',
                '| ![그림](image.png) | [본문](#body) |',
                '| <a id="legacy"></a>내용 | 목적지 없음 |',
                '| 내용 | [본문](#body) 뒤에 추가 지시 |'):
        rendered, _, _ = _render('| 지금 확인할 내용 | 이동할 절 |\n|---|---|\n' + row,
                                 'a.md', {'other.md'}, None, '', '')
        assert '<table>' in rendered and '지금 확인할 내용' in rendered


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
