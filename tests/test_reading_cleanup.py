import re

import pytest

from sdd.reading_cleanup import compact_tables, class_targets, link_related_classes, merge_next_step


def table(headers, rows):
    return ('<table><thead><tr>' + ''.join('<th>' + h + '</th>' for h in headers)
            + '</tr></thead><tbody>' + ''.join('<tr>' + ''.join('<td>' + c + '</td>' for c in row) + '</tr>' for row in rows)
            + '</tbody></table>')


def coverage(scope='코드 근거와 설명 연결'):
    return ('<details class="note"><summary>설계 질문과 검증 범위</summary>'
            '<p>질문별 답변과 근거 연결을 검사했습니다. 의미와 실행 결과는 사람 검토가 필요합니다.</p>'
            + table(['설계 질문', '설명 위치', '확인 범위'], [
                ['<code>Request</code>의 수명은?', '<a href="#life">수명</a>', scope],
                ['실행 검증은?', '<a href="#verify">검증</a>', '코드 근거와 설명 연결 · 실행 확인 항목 별도']]) + '</details>')


def test_coverage_list_keeps_questions_links_scope_and_human_review_boundary():
    source = coverage()
    result = compact_tables(source)
    assert '<table' not in result and '<ul class="coverage-links">' in result
    assert '<code>Request</code>의 수명은?' in result and '실행 검증은?' in result
    assert re.findall(r'href="([^"]+)"', result) == re.findall(r'href="([^"]+)"', source)
    assert result.count('코드 근거와 설명 연결') == 1
    assert '실행 확인 항목 별도' in result and '의미와 실행 결과는 사람 검토가 필요합니다.' in result
    assert compact_tables(result) == result


def test_custom_coverage_scope_and_example_html_stay_intact():
    source = coverage('사용자 정의 검증 조건')
    assert compact_tables(source) == source
    source = coverage().replace('<td>', '<td title="context">', 1)
    assert compact_tables(source) == source
    source = '<pre>' + coverage() + '</pre>'
    assert compact_tables(source) == source


def test_single_call_becomes_labeled_record_without_losing_boundary_or_citations():
    headers = ['호출 지점', '후보 또는 예약 대상', '확인할 경계', '근거']
    row = ['Camera', '<code>Pipe::queue()</code>', '메서드 전달이며 비동기 보장이 아닙니다.', '<a href="code#L9">src/a.cpp:9</a>']
    result = compact_tables(table(headers, [row]))
    assert '<table' not in result and '<dl class="call-checkpoint">' in result
    assert all('<dt>' + header + '</dt>' in result for header in headers)
    assert all('<dd>' + cell + '</dd>' in result for cell in row)
    source = table(headers, [row, row])
    assert compact_tables(source) == source


def test_one_row_code_index_and_anchored_table_are_not_changed():
    source = table(['클래스', '선언 위치', '상속', '책임 (주석)'], [['Camera', 'a.h:1', 'Base', 'Camera']])
    assert compact_tables(source) == source
    for tag in ('th', 'td', 'tr'):
        custom = source.replace('<' + tag + '>', '<' + tag + ' aria-label="context">', 1)
        assert compact_tables(custom) == custom
    source = table(['확인할 내용', '호출 측과 대상', '구분', '근거'], [['<a id="keep"></a>check', 'call', 'note', 'a:1']])
    assert compact_tables(source) == source


CLASS_HEADERS = ['클래스', '선언 위치', '상속', '책임 (주석)']
ROW = ['<code>Camera</code>', '<a href="https://host/blob/hash/a.h#L1"><code>a.h:1</code></a>', '<code>Base</code>', 'A camera']


def index(row=ROW, anchor='symbol-1111111111111111'):
    return table(CLASS_HEADERS, [row]).replace('<tbody><tr>', '<tbody><tr id="' + anchor + '" tabindex="-1" data-symbol-kind="class">')


def related(row=ROW):
    return ('<h2 id="관련-클래스">관련 클래스</h2>\n'
            '<div class="table-scroll stack" tabindex="0" role="region" aria-label="표">'
            + table(CLASS_HEADERS, [row]) + '</div>')


def test_reference_links_require_exact_unique_full_row_and_use_relative_destination():
    targets = class_targets({'reference/index.html': index()})
    result = link_related_classes(related(), 'guides/camera.html', targets)
    assert '<table' not in result and 'id="관련-클래스"' in result
    assert '<a href="../reference/index.html#symbol-1111111111111111"><code>Camera</code></a>' in result
    assert link_related_classes(related([*ROW[:3], 'Different responsibility']), 'camera.html', targets) == related([*ROW[:3], 'Different responsibility'])
    assert link_related_classes(related(), 'camera.html', class_targets({'a.html': index(), 'b.html': index()})) == related()
    assert link_related_classes(related(), 'camera.html', {}) == related()


def test_partial_reference_matches_do_not_drop_unmatched_rows():
    source = related().replace('</tbody>', '<tr><td>Missing</td><td>m.h:2</td><td>–</td><td>Unique</td></tr></tbody>')
    assert link_related_classes(source, 'camera.html', class_targets({'index.html': index()})) == source


def test_custom_reference_attributes_and_linked_names_remain_intact():
    for tag in ('th', 'td', 'tr'):
        source = related().replace('<' + tag + '>', '<' + tag + ' title="context">', 1)
        assert link_related_classes(source, 'camera.html', class_targets({'index.html': index()})) == source
    row = ['<a href="other.html">Camera</a>', *ROW[1:]]
    assert link_related_classes(related(row), 'camera.html', class_targets({'index.html': index(row)})) == related(row)
    assert class_targets({'index.html': index().replace('<td>', '<td title="context">', 1)}) != class_targets({'index.html': index()})


@pytest.mark.parametrize('extra', ['<caption>Important conditions</caption>', '<tfoot><tr><td>Exception</td></tr></tfoot>', 'Additional instructions'])
def test_custom_table_content_outside_cells_is_never_discarded(extra):
    sources = [coverage(), table(['확인할 내용', '호출 측과 대상', '구분', '근거'], [['point', 'call', 'note', 'source']])]
    for source in sources:
        custom = source.replace('<table>', '<table>' + extra, 1)
        assert compact_tables(custom) == custom
    custom = related().replace('<table>', '<table>' + extra, 1)
    assert link_related_classes(custom, 'camera.html', class_targets({'index.html': index()})) == custom


def test_call_form_guidance_changes_only_for_converted_records_and_not_code_examples():
    instruction = '주요 확인 지점 1개를 아래 표와 관계도에 표시합니다.'
    source = '<p>' + instruction + '</p>' + table(['확인할 내용', '호출 측과 대상', '구분', '근거'], [['point', 'call', 'note', 'source']])
    result = compact_tables(source + '<pre>' + instruction + '</pre>')
    assert '<p>주요 확인 지점 1개를 아래 목록과 관계도에 표시합니다.</p>' in result
    assert '<pre>' + instruction + '</pre>' in result
    assert compact_tables('<p>' + instruction + '</p>') == '<p>' + instruction + '</p>'


def test_matching_next_link_is_one_control_and_distinct_hint_survives():
    control = '<a class="next" href="request.html#life"><small>다음</small>요청 수명 →</a>'
    source = '<h2 id="keep">내용</h2><p>다음 단계: <a href="request.html#life">요청 수명</a></p>'
    content, result = merge_next_step(source, control)
    assert content == '<h2 id="keep">내용</h2>' and result == control
    content, result = merge_next_step(source.replace('>요청 수명</a>', '>실패 후 복구 확인</a>'), control)
    assert content == '<h2 id="keep">내용</h2>'
    assert '실패 후 복구 확인' in result and '요청 수명' in result and result.count('href=') == 1


@pytest.mark.parametrize('tail', [
    '<p>다음 단계: <a href="request.html#different">요청 수명</a></p>',
    '<p>다음 단계: <a id="legacy" href="request.html#life">요청 수명</a></p>',
    '<pre><p>다음 단계: <a href="request.html#life">요청 수명</a></p></pre>',
    '<p>다음 단계: <a href="request.html#life">요청 수명</a>과 추가 지시</p>',
])
def test_distinct_targets_custom_attributes_examples_and_extra_instructions_are_retained(tail):
    control = '<a class="next" href="request.html#life"><small>다음</small>요청 수명 →</a>'
    assert merge_next_step(tail, control) == (tail, control)


def test_generated_status_groups_preserve_all_pages_and_nonpassing_states(tmp_cfg, sample_model):
    from test_export_site import prepare
    from sdd.export_site import export_site
    prepare(tmp_cfg, sample_model)
    path = tmp_cfg.sdd_dir / 'nested/detail.md'
    path.write_text(path.read_text(encoding='utf-8').replace('needs-review', 'ok'), encoding='utf-8')
    out = export_site(tmp_cfg)
    page = (out / 'index.html').read_text(encoding='utf-8')
    assert '<h2 id="문서-목록">문서 검증 현황</h2>' in page
    assert '<th>검사 결과</th>' not in page
    assert '<span>인용 검사 확인 필요</span>' in page and '<span>인용 검사 통과</span>' in page
    assert page.count('<span>사람 검토 전</span>') >= 2
    assert 'href="device.html"' in page and 'href="nested/detail.html"' in page
