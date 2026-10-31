from sdd.product_context import SIMULATION_NOTICE
from sdd.reading_cleanup import fold_scope_notices
from sdd.site_markdown import _render


NOTICE = '<p><strong>' + SIMULATION_NOTICE.strip('*') + '</strong></p>'


def test_scope_is_folded_once_with_each_original_section_and_next_step_intact():
    source = ('<h2 id="real">실제 제품</h2><p>지원 조건</p>'
              '<h2 id="a">시험 A</h2>' + NOTICE + '<p>관측된 결과</p>'
              '<h2 id="b">시험 B</h2>' + NOTICE + '<p>추가 조건</p>'
              '<h2 id="소스-근거">소스 근거</h2><p>원문</p>'
              '<p>다음 단계: <a href="next.html">절차</a></p>')
    result = fold_scope_notices(source)
    assert result.count(NOTICE) == 1
    assert '<summary>가상 시험의 검증 범위</summary>' in result
    assert '<a href="#a">시험 A</a>' in result and '<a href="#b">시험 B</a>' in result
    assert '<a href="#real">' not in result
    assert result.index('<details') < result.index('<h2 id="소스-근거">')
    assert result.endswith('<p>다음 단계: <a href="next.html">절차</a></p>')
    assert fold_scope_notices(result) == result


def test_code_custom_warnings_and_unscoped_notices_remain_visible_and_unchanged():
    unscoped = NOTICE + '<h2 id="a">A</h2>'
    assert fold_scope_notices(unscoped) == unscoped
    custom = '<h2 id="a">A</h2><p class="warning">장치 권한을 먼저 확인하세요.</p>'
    assert fold_scope_notices(custom) == custom
    code = '<h2 id="a">A</h2><pre>' + NOTICE + '</pre>'
    assert fold_scope_notices(code) == code


def test_normal_render_folds_display_without_rewriting_manuscript_or_raw_evidence():
    original = ('## 결과\n\n' + SIMULATION_NOTICE + '\n\n가상 캡처가 완료됐습니다.\n\n'
                '## 소스 근거\n\n```json\n{"pid":434,"status":1}\n```\n')
    result, _, _ = _render(original, 'trial.md', {'trial.md'}, None, '', '')
    assert '<details class="note scope-notices">' in result
    assert result.index('가상 캡처가 완료됐습니다.') < result.index('가상 시험의 검증 범위')
    assert '434' in result and 'status' in result
    assert original.count(SIMULATION_NOTICE) == 1


def test_diagram_follows_explanation_after_scope_notice_is_folded():
    from sdd.visuals import place
    topic={'id':'result','title':'결과','_product_context':{'product':{'simulation':True}}}
    text='## 결과\n\n'+SIMULATION_NOTICE+'\n\n핵심 설명입니다.\n\n조건 설명입니다.\n'
    result=place(text,[({'topic':'result'},'### 질문별 그림\n\n그림 원문','graph')],{'design_topics':[topic]})
    assert result.index('핵심 설명입니다.')<result.index('질문별 그림')<result.index('조건 설명입니다.')
