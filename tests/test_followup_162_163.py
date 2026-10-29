"""Public residual failures, distinct from existing argument/guard regressions."""
import json
from pathlib import Path
from types import SimpleNamespace

from sdd.duplicates import statement_findings
from sdd.generate import _routes_from_headings
from sdd.config import load
import markdown


def test_original_crop_retry_remains_rejected():
    data = json.loads((Path(__file__).parent / 'fixtures/crop-repetition-162.json').read_text(encoding='utf-8'))
    model = SimpleNamespace(evidence={'ipu3-lsc-prepare/prepare/prepare': data['evidence']})
    found = statement_findings(model, 'ipu3-lsc-prepare', {'prepare': data['answers']})
    assert found and '[의미 중복]' in found[0]


def test_original_buffer_lifetime_retry_remains_rejected():
    data = json.loads((Path(__file__).parent / 'fixtures/buffer-lifetime-repetition-163.json').read_text(encoding='utf-8'))
    model = SimpleNamespace(evidence={'camera-requests/' + k: v for k, v in data['evidence'].items()})
    assert data['answers']['lifetime'][0]['text'] == json.loads(data['raw_retry_response'])['statements'][0]['text']
    found = statement_findings(model, 'camera-requests', data['answers'])
    assert found and '[의미 중복]' in found[0]


def test_scenario_navigation_uses_content_and_preserves_identifiers():
    body = ('## 이 흐름에서 확인할 것\n\n`Camera::queueRequest()`에서 정적 호출을 찾습니다. 다음 문장입니다.\n\n'
            '## 주요 확인 지점\n\n아래 항목은 코드 탐색 지점이며 실행 순서가 아닙니다.\n\n'
            '## 전체 추적 기록\n\n| 기록 | 대상 |\n|---|---|\n| 1 | x |')
    assert _routes_from_headings(body) == [
        ('`Camera::queueRequest()`에서 정적 호출을 찾습니다.', '#이-흐름에서-확인할-것'),
        ('아래 항목은 코드 탐색 지점이며 실행 순서가 아닙니다.', '#주요-확인-지점')]


def test_heading_navigation_does_not_invent_table_or_code_only_leads():
    body = ('## 첫 제목\n\n첫 제목 절을 확인합니다.\n\n## 두 제목\n\n'
            '```cpp\nsource();\n\nnot_a_lead();\n```\n\n| 표 | 행 |\n\n'
            '## 소스 근거\n\n원문입니다.')
    assert _routes_from_headings(body) is None


def test_combined_questions_preserve_all_unique_argument_and_completion_contracts():
    cfg = load(Path(__file__).parents[1] / 'examples/libcamera/sdd.yaml')
    def parts(section, topic):
        sec = next(s for s in cfg.sections() if s['id'] == section)
        return next(t for t in sec['design_topics'] if t['id'] == topic)['parts']
    arguments = next(p for p in parts('ipu3-lsc-flow', 'request') if p['id'] == 'arguments')
    assert arguments['sources'] == ['delegate-call']
    assert arguments['answer_contract']['required_terms'] == [
        ['context.activeState.lsc'], ['frameContext.lsc'], ['controls']]
    completion = next(p for p in parts('vendor-integration', 'request') if p['id'] == 'completion')
    assert completion['sources'] == ['completion', 'notification']
    assert completion['answer_contract']['basis'] == 'contract'
    assert all('notification' != p['id'] for p in parts('vendor-integration', 'request'))
    buffer = next(p for p in parts('vendor-integration', 'request') if p['id'] == 'buffer')
    assert buffer['sources'] == ['buffer', 'completion-context']
    assert ['CameraManager'] in buffer['answer_contract']['required_terms']
    assert all('completion-context' != p['id'] for p in parts('vendor-integration', 'request'))
    assert all('buffer-lifetime' != p['id'] for p in parts('camera-requests', 'request'))
    validity = next(p for p in parts('camera-requests', 'lifetime') if p['id'] == 'buffer-validity')
    assert validity['sources'] == ['buffer']
    assert validity['answer_contract'] == {'basis': 'contract', 'required_terms': [['버퍼'], ['콜백']]}
    enable = next(p for p in parts('ipu3-lsc-prepare', 'prepare') if p['id'] == 'enable')
    assert enable['sources'] == ['enable-branch']
    assert enable['answer_contract']['required_terms'] == [['shd_enable'], ['enabled'], ['반환', 'return']]


def test_navigation_ignores_headings_in_both_fence_kinds_and_resumes_after_close():
    body = ('## 실제 절\n\n```cpp\n## 가짜 절\n문서가 아닙니다.\n```\n'
            '호출 지점을 코드와 대조합니다.\n\n## 다른 절\n\n~~~cpp\n## 가짜 제목\n~~~\n'
            '반환값과 실패 조건을 확인합니다.')
    assert _routes_from_headings(body) == [
        ('호출 지점을 코드와 대조합니다.', '#실제-절'),
        ('반환값과 실패 조건을 확인합니다.', '#다른-절')]


def test_navigation_ignores_indented_code_and_keeps_following_prose():
    body = ('## 코드만 있는 절\n\n    call();\n\n\tother();\n\n'
            '## 설명이 있는 절\n\n    call();\n설정과 실제 호출을 대조합니다.\n\n'
            '## 다음 설명\n\n실패한 요청의 반환값을 확인합니다.')
    assert _routes_from_headings(body) == [
        ('설정과 실제 호출을 대조합니다.', '#설명이-있는-절'),
        ('실패한 요청의 반환값을 확인합니다.', '#다음-설명')]


def test_navigation_ignores_html_comment_headings_and_tables_without_leading_pipe():
    body = ('<!--\n## 숨긴 제목\n보여서는 안 됩니다.\n-->\n\n'
            '## 표만 있는 절\n\nName | Value\n--- | ---\na | b\n\n'
            '## 실제 설명\n\n호출 책임을 근거와 대조합니다.\n\n'
            '## 다른 설명\n\n반환 조건을 확인합니다.')
    assert _routes_from_headings(body) == [
        ('호출 책임을 근거와 대조합니다.', '#실제-설명'),
        ('반환 조건을 확인합니다.', '#다른-설명')]


def test_navigation_stops_at_h1_and_preserves_pipe_expressions_in_code():
    body = ('## 비어 있는 절\n\n# 새 문서\n\n다른 문서의 설명입니다.\n\n'
            '## 식 설명\n\n`a | b`를 계산하고 x | y도 구분합니다.\n\n'
            '## 다른 설명\n\n반환값을 확인합니다.')
    routes = _routes_from_headings(body)
    assert routes == [('`a | b`를 계산하고 x &#124; y도 구분합니다.', '#식-설명'),
                      ('반환값을 확인합니다.', '#다른-설명')]
    table = '| 내용 | 이동 |\n|---|---|\n' + '\n'.join(f'| {q} | [절]({target}) |' for q, target in routes)
    html = markdown.markdown(table, extensions=['tables'])
    assert '<code>a | b</code>' in html and html.count('<td>') == 4
