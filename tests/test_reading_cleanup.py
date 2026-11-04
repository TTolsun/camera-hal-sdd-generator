import re
import hashlib

import pytest

from sdd.reading_cleanup import compact_tables, class_targets, link_related_classes, merge_next_step, promote_coverage


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


def test_observed_writer_directions_are_not_reader_questions():
    technical = ('Running 상태와 -ENODEV/-EACCES를 설명하세요. '
                 '반환값 0과 requestCompleted를 구분하세요.')
    directions = ('세 문단 이내로 작성하세요. '
                  '각 문단은 한 가지 독자 과업을 설명하고, 같은 결과나 반환값을 다시 풀어 쓰지 마세요. '
                  '소스 한 줄마다 문단을 만들지 마세요. '
                  '아래 절에서 설명하는 내부 구현을 미확인 한계로 반복하지 마세요.')
    source = coverage().replace('<code>Request</code>의 수명은?', technical + ' ' + directions)
    spec = {hashlib.sha256((technical + ' ' + directions).encode()).hexdigest(): [
        '세 문단 이내로 작성하세요.',
        '각 문단은 한 가지 독자 과업을 설명하고, 같은 결과나 반환값을 다시 풀어 쓰지 마세요.',
        '소스 한 줄마다 문단을 만들지 마세요.',
        '아래 절에서 설명하는 내부 구현을 미확인 한계로 반복하지 마세요.']}
    result = compact_tables(source, question_edits=spec)
    assert technical in result
    assert '세 문단' not in result and '소스 한 줄마다' not in result
    assert re.findall(r'href="([^"]+)"', source) == re.findall(r'href="([^"]+)"', result)
    assert compact_tables(result) == result
    with pytest.raises(ValueError, match='changed or is absent'):
        compact_tables(source.replace('Running', 'Stopped'), question_edits=spec)
    with pytest.raises(ValueError, match='changed or is absent'):
        compact_tables(source.replace('코드 근거와 설명 연결 · 실행 확인 항목 별도', '사용자 정의 조건'), question_edits=spec)
    # Contract imperatives, code literals, custom notes and empty-only rows
    # must never be generalized into the editorial-removal rule.
    assert directions in compact_tables(source.replace(technical + ' ' + directions, directions))
    code = source.replace(technical + ' ' + directions, '<code>세 문단 이내로 작성하세요.</code> 호출 의무를 유지하세요.')
    assert '<code>세 문단 이내로 작성하세요.</code> 호출 의무를 유지하세요.' in compact_tables(code)
    for protected in ['<code> 세 문단 이내로 작성하세요. </code>', '<a href="#life"> 세 문단 이내로 작성하세요. </a>',
                      '<samp> 세 문단 이내로 작성하세요. </samp>', '<em> 세 문단 이내로 작성하세요. </em>']:
        example = coverage().replace('<code>Request</code>의 수명은?', protected + ' 계약을 확인하세요.')
        assert protected in compact_tables(example)
    markup = '<span title=" 세 문단 이내로 작성하세요. > ">기술 조건</span>'
    assert markup in compact_tables(coverage().replace('<code>Request</code>의 수명은?', markup + ' 세 문단 이내로 작성하세요.'))
    example = '<code><br></br> 세 문단 이내로 작성하세요. </unmatched></code>'
    assert example in compact_tables(coverage().replace('<code>Request</code>의 수명은?', example))
    for quoted in ['인용문: " 세 문단 이내로 작성하세요. "는 기존 요구사항입니다.',
                   '“앞 문장. 세 문단 이내로 작성하세요.”를 그대로 보존하세요.',
                   '계약의 일부로 세 문단 이내로 작성하세요. 조건을 인용합니다.',
                   '계약 조건은 다음과 같습니다. 세 문단 이내로 작성하세요. 이 조건은 필수입니다.']:
        assert quoted in compact_tables(coverage().replace('<code>Request</code>의 수명은?', quoted))


@pytest.mark.parametrize('remaining', ['<br>', '<!-- empty -->', '<span></span>',
                                    '<script>ignored</script>', '<style>ignored</style>',
                                    '<template>ignored</template>', '<span hidden>ignored</span>',
                                    '<span style="display:none">ignored</span>', '&nbsp;',
                                    '<span>&#8203;</span>', '&#xfeff;', '???'])
def test_configured_removal_cannot_leave_only_markup(remaining):
    question = '세 문단 이내로 작성하세요. ' + remaining
    source = coverage().replace('<code>Request</code>의 수명은?', question)
    edits = {hashlib.sha256(question.encode()).hexdigest(): ['세 문단 이내로 작성하세요.']}
    with pytest.raises(ValueError, match='empty a question'):
        compact_tables(source, question_edits=edits)


def test_configured_removal_preserves_visible_entity_text():
    question = '세 문단 이내로 작성하세요. &#65;'
    source = coverage().replace('<code>Request</code>의 수명은?', question)
    edits = {hashlib.sha256(question.encode()).hexdigest(): ['세 문단 이내로 작성하세요.']}
    assert '&#65;' in compact_tables(source, question_edits=edits)


def test_question_guide_follows_lead_before_terms_with_content_and_links_intact():
    lead = '<p><strong>도입할 범위를 판단하세요.</strong></p>'
    terms = '<details class="page-terms"><summary>용어</summary><p>Camera</p></details>'
    body = '<h2 id="life">수명</h2><p>본문</p><h2 id="verify">검증</h2>'
    guide = compact_tables(coverage())
    result = promote_coverage(lead + terms + body + guide)
    assert result == lead + guide + terms + body
    assert promote_coverage(result) == result
    assert ' open' not in result


def test_question_guide_without_lead_precedes_body_but_examples_and_custom_notes_stay():
    guide = compact_tables(coverage())
    body = '<h2 id="life">수명</h2>'
    assert promote_coverage(body + guide) == guide + body
    for source in ('<pre>' + guide + '</pre>', coverage('사용자 정의 검증 조건'),
                   body + guide + guide):
        assert promote_coverage(source) == source


def test_manuscript_review_records_deduplicate_exact_values_but_keep_history():
    from sdd.reading_cleanup import collect_manuscript_records
    note = ('<details class="note"><summary>근거와 검토 정보</summary><ul>'
            '<li>생성 방식: 추출 사실과 LLM 설명</li><li>검증 범위: 과거 범위</li>'
            '<li>근거 수준: commit <code>old</code></li><li>검토 상태 기록일: 과거 날짜</li>'
            '<li><a href="record.json">기록</a></li></ul></details>')
    current = {'생성 방식': '추출 사실과 LLM 설명', '검증 범위': '현재 범위'}
    content, record = collect_manuscript_records('<p>본문</p>' + note, current)
    assert content == '<p>본문</p>'
    assert '생성 방식:' not in record
    for value in ('과거 범위', '<code>old</code>', '과거 날짜', 'href="record.json"'):
        assert value in record
    assert '원고 작성 당시 기록' in record
    assert collect_manuscript_records(content, current) == (content, '')
    assert collect_manuscript_records('<pre>' + note + '</pre>', current) == ('<pre>' + note + '</pre>', '')
    scoped = note.replace('근거와 검토 정보</summary>', '근거와 검토 정보: package</summary>')
    assert '생성 방식:' in collect_manuscript_records(scoped, current)[1]


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


def test_pagination_merges_same_destination_into_the_requested_next_step():
    from sdd.export_site import _pagination_html
    entries = [('', '지원 범위와 검증', 'assurance.md'), ('', '연동', 'integration.md'), ('', '상세', 'detail.md')]
    links = _pagination_html(entries, {'integration.md': {'next': {'link': 'assurance.md'}}},
                             1, 'integration.md', 'integration.html')
    assert links == ['<a class="next" href="assurance.html"><small>다음</small>지원 범위와 검증 →</a>']


@pytest.mark.parametrize('destination', ['assurance.md#scope', 'detail.md'])
def test_pagination_keeps_distinct_page_or_fragment_destinations(destination):
    from sdd.export_site import _pagination_html
    entries = [('', '같은 제목', 'assurance.md'), ('', '연동', 'integration.md'), ('', '같은 제목', 'detail.md')]
    links = _pagination_html(entries, {'integration.md': {'next': {'link': destination}}},
                             1, 'integration.md', 'integration.html')
    assert len(links) == 2
    assert links[0].startswith('<a class="previous" href="assurance.html">')
    assert ('href="' + destination.replace('.md', '.html') + '"') in links[1]
