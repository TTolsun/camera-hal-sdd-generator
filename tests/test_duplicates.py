"""A1: 같은 근거로 같은 뜻을 되풀이한 문장을 결정적으로 반려한다.

문장 쌍은 공개 libcamera 문서(분석 커밋 2c4b67c0)에서 실제로 나온 것이다."""
from types import SimpleNamespace

import pytest

from sdd.duplicates import body_findings, repeated_topics, similar, statement_findings

REPEATED = [
    ("공통 queueRequest 의 요청 추적이 stop() 시 완료와 어떤 관계가 있는지는, 파이프라인 핸들러가 stop() 으로 중지될 때 "
     "대기 중인 모든 요청이 자동으로 완료되도록 보장하며, 이때 completeRequest() 함수를 사용하여 요청 완료를 신호로 전달합니다.",
     "파이프라인 핸들러는 stop()으로 파이프라인이 중지될 때 대기 중인 모든 요청의 완료를 보장하기 위해 "
     "completeRequest() 함수를 사용하여 완료 신호를 보내야 합니다."),
    ("호출자는 Camera::createRequest() 가 반환하는 요청의 소유권을 가지며, 완료 처리기에서 삭제하거나 Request::reuse() 로 "
     "상태를 초기화한 후 재사용해야 합니다.",
     "Camera::createRequest 함수가 생성한 요청은 완료 핸들러에서 삭제하거나 Request::reuse() 를 호출하여 "
     "상태를 초기화한 뒤 재사용할 수 있습니다."),
    ("generateConfiguration 은 요청된 roles 이 충족될 경우 유효한 CameraConfiguration 을 반환하고, 그렇지 않으면 null 포인터를 반환해야 합니다.",
     "generateConfiguration 메서드는 요청된 역할 목록을 충족할 수 있으면 유효한 CameraConfiguration 객체를 반환하고, "
     "그렇지 않으면 null 포인터를 반환합니다."),
]
DISTINCT = [
    ("CameraConfiguration::Adjusted는 구성이 조정되어 이제 유효함을 나타냅니다.",
     "CameraConfiguration::Valid 상태는 이미 유효한 구성으로 조정되지 않은 경우를 나타냅니다."),
    ("CameraConfiguration::Adjusted는 구성이 조정되어 이제 유효함을 나타냅니다.",
     "CameraConfiguration::Adjusted 일 때 호출자는 설정을 신중하게 확인해야 합니다."),
    ("Camera::createRequest() 함수는 카메라가 Configured 상태이거나 Running 상태일 때만 호출할 수 있습니다.",
     "호출자는 Camera::createRequest() 가 반환하는 요청의 소유권을 가지며, 완료 처리기에서 삭제하거나 Request::reuse() 로 "
     "상태를 초기화한 후 재사용해야 합니다."),
    ("PipelineHandler 클래스의 생성자는 maxQueuedRequestsDevice 인자의 기본값을 32로 설정합니다.",
     "PipelineHandler::maxQueuedRequestsDevice_ 가 제한하는 요청 수는 하드웨어로 직접 대기 중인 요청의 최대 개수에 해당하며, "
     "초과된 요청은 내부 대기 큐에 남아 나중에 처리됩니다."),
]


def test_공개_문서에서_나온_중복_문장_쌍을_잡는다():
    assert all(similar(a, b) for a, b in REPEATED)


def test_같은_근거의_서로_다른_조건_문장은_중복이_아니다():
    assert not any(similar(a, b) for a, b in DISTINCT)


def _model(**sha):
    return SimpleNamespace(evidence={f"s/{key}": {"sha256": value} for key, value in sha.items()})


def _statement(text, ref):
    return {"text": text, "evidence": [ref]}


def test_같은_발췌를_인용한_중복만_지적하고_첫_문장은_남긴다():
    a, b = REPEATED[0]
    model = _model(**{"t1/x": "h1", "t2/x": "h1", "t3/x": "h2"})
    same = {"t1": [_statement(a, "x")], "t2": [_statement(b, "x")]}
    findings = statement_findings(model, "s", same)
    assert len(findings) == 1 and "[의미 중복]" in findings[0] and "t2 1번째" in findings[0] and "t1 1번째" in findings[0]
    other_source = {"t1": [_statement(a, "x")], "t3": [_statement(b, "x")]}
    assert statement_findings(model, "s", other_source) == []


def test_이미_통과한_앞_문장끼리는_다시_지적하지_않는다():
    a, b = REPEATED[1]
    model = _model(**{"t/x": "h"})
    statements = {"t": [_statement(a, "x"), _statement(b, "x")]}
    assert len(statement_findings(model, "s", statements)) == 1
    assert statement_findings(model, "s", statements, only_after={"t": 2}) == []


def test_재사용할_이전_답변이_앞_주제와_겹치면_뒤_주제를_다시_만들게_한다():
    a, b = REPEATED[2]
    model = _model(**{"t1/x": "h", "t2/x": "h"})
    section = {"id": "s", "design_topics": [{"id": "t1"}, {"id": "t2"}]}
    answers = {"t1": [_statement(a, "x")], "t2": [_statement(b, "x")]}
    assert repeated_topics(model, section, answers) == ["t2"]


def test_본문에서_같은_인용을_공유한_중복_문장을_행_번호와_함께_돌려준다():
    a, b = REPEATED[0]
    body = f"{a} `src/p.cpp:10`\n\n{b} `src/p.cpp:10`"
    found = body_findings(body)
    assert [line for line, _, _ in found] == [3]
    assert "1행" in found[0][2]
    different_citation = f"{a} `src/p.cpp:10`\n\n{b} `src/q.cpp:99`"
    assert body_findings(different_citation) == []


# Frozen public-corpus false positives, including the newly exposed temperature pair.
DISTINCT_CLAIMS = [('`Camera::queueRequest()` 함수는 요청의 제어 목록 정보가 카메라의 현재 제어 목록과 일치하지 않으면 `-EINVAL` 오류를 반환합니다.',
  '`Camera::queueRequest()` 함수는 요청의 각 스트림이 활성 스트림 목록에 존재하지 않으면 `-EINVAL` 오류를 반환합니다.',
  '/* Make sure the Request has a valid control list. */\n'
  '\tif (request->controls().infoMap() != &controls()) {\n'
  '\t\tLOG(Camera, Error) << "Overwriting Request::controls() is not allowed";\n'
  '\t\treturn -EINVAL;\n'
  '\t}',
  'for (const auto &[stream, buffer] : request->buffers()) {\n'
  '\t\tif (d->activeStreams_.find(stream) == d->activeStreams_.end()) {\n'
  '\t\t\tLOG(Camera, Error) << "Invalid request";\n'
  '\t\t\treturn -EINVAL;\n'
  '\t\t}\n'
  '\t}'),
 ('`IPCPipeUnixSocket::sendSync` 함수는 호출이 실패하면 에러 로그를 출력하고 음수 반환 값을 반환하며, 타임아웃이 발생하면 `-ETIMEDOUT`을 '
  '반환합니다.',
  '`IPCPipeUnixSocket::call` 함수는 타임아웃이 발생하면 `-ETIMEDOUT`을 반환하고, 호출 실패 시 음수 값을 반환하며, 성공하면 `0`을 '
  '반환합니다.',
  '',
  ''),
 ('`createDMABufTexture2D()` 함수의 `switch` 문에서 기본(`default`) 분기가 실행되면, 처리되지 않은 GL 포맷에 대해 오류 로그가 '
  '출력됩니다.',
  '`createDMABufTexture2D()` 함수의 `switch` 문에서 기본(`default`) 분기가 실행되면, `-ENODEV`를 반환합니다.',
  '',
  ''),
 ('`createInputDMABufTexture2D()` 함수는 내부적으로 `createDMABufTexture2D()` 함수를 호출할 때 마지막 인자로 `false` 값을 '
  '전달합니다.',
  '`createOutputDMABufTexture2D()` 함수는 내부적으로 `createDMABufTexture2D()` 함수를 호출할 때 마지막 인자로 `true` 값을 '
  '전달합니다.',
  '',
  ''),
 ('첫 번째 프레임이고 LensShadingCorrectionEnable 제어가 없을 때, `frameContext.lsc.enabled`에는 `true`가 쓰입니다.',
  '첫 번째 프레임이고 LensShadingCorrectionEnable 제어가 없을 때, `Lsc::queueRequest` 함수는 '
  'frameContext.lsc.update 필드에 true 값을 설정합니다.',
  '',
  ''),
 ('`Lsc::queueRequest` 함수가 호출될 때 첫 번째 인자로 전달되는 값은 `context.activeState.lsc` 입니다.',
  '`frameContext.lsc` 는 `Lsc::queueRequest` 함수 호출의 두 번째 인자로 전달되며, 이 값은 해당 프레임 컨텍스트에서 관리되는 렌즈 음영 보정 '
  '상태 정보를 나타냅니다.',
  '',
  ''),
 ('`Lsc::prepare` 함수는 `frameContext.lsc.update` 가 false 이고 `frameContext.lsc.enabled` 도 false 인 경우 '
  '즉시 반환합니다.',
  '`Lsc::prepare` 함수는 `frameContext.lsc.update` 가 false 이고 `frameContext.lsc.enabled` 가 true 일 때, '
  '현재 색온도 (`ct`) 와 마지막 적용된 색온도 (`lastAppliedCt_`) 의 차이가 `kColourTemperatureQuantization`(10) 을 2 로 '
  '나눈 값보다 작으면 조기 반환합니다.',
  '',
  ''),
 ('`Lsc::prepare` 함수는 `frameContext.lsc.update` 가 false 이고 `frameContext.lsc.enabled` 도 false 인 경우 '
  '즉시 반환합니다.',
  '`Lsc::prepare` 함수는 `frameContext.lsc.update` 가 false 이고 `frameContext.lsc.enabled` 가 true 일 때, '
  '현재 양자화된 색온도 (`quantizedCt`) 와 마지막으로 적용된 양자화된 색온도 (`lastAppliedQuantizedCt_`) 의 차이가 '
  '`kColourTemperatureQuantization / 2` 보다 작으면 조기 반환합니다.',
  '',
  ''),
 ('`Lsc::prepare` 함수의 활성 경로에서 `config->grid.width`는 멤버 변수인 `numHCells_`로 설정되고, '
  '`config->grid.height`는 `numVCells_`로 설정되며, `config->grid.grid_height_per_slice`는 상수 '
  '`IPU3_UAPI_SHD_MAX_CELLS_PER_SET`를 `numHCells_`로 나눈 값으로 설정됩니다.',
  '`Lsc::prepare` 함수의 활성 경로에서 `config->general.gain_factor` 멤버 변수에는 항상 `0`이 설정됩니다.',
  '',
  ''),
 ('`PipelineHandler::configure()` 함수는 `CameraManager` 스레드에서 호출되며, 성공 시에는 0 을 반환하고 실패 시에는 음수 오류 코드를 '
  '반환해야 합니다.',
  '`PipelineHandler::queueRequestDevice()` 함수는 `CameraManager` 스레드에서 호출되어야 하며, 성공 시에는 0 을 반환하고 실패 '
  '시에는 음수 오류 코드를 반환해야 합니다.',
  '',
  ''),
 ('`Lsc::prepare` 함수는 `frameContext.lsc.update` 가 false 이고 `frameContext.lsc.enabled` 가 true 일 때, '
  '현재 색온도 (`ct`) 와 마지막 적용된 색온도 (`lastAppliedCt_`) 의 차이가 `kColourTemperatureQuantization`(10) 을 2 로 '
  '나눈 값보다 작으면 조기 반환합니다.',
  '`Lsc::prepare` 함수는 `frameContext.lsc.update` 가 false 이고 `frameContext.lsc.enabled` 가 true 일 때, '
  '현재 양자화된 색온도 (`quantizedCt`) 와 마지막으로 적용된 양자화된 색온도 (`lastAppliedQuantizedCt_`) 의 차이가 '
  '`kColourTemperatureQuantization / 2` 보다 작으면 조기 반환합니다.',
  '',
  '')]


@pytest.mark.parametrize('left,right,left_quote,right_quote', DISTINCT_CLAIMS)
def test_explicitly_different_public_claims_are_not_duplicates(left, right, left_quote, right_quote):
    model = _model(**{'t/x': 'same-excerpt'})
    answers = {'t': [dict(text=left, quote=left_quote, evidence=['x']),
                     dict(text=right, quote=right_quote, evidence=['x'])]}
    assert statement_findings(model, 's', answers) == []


def test_function_alias_keeps_repetition_but_explicit_owners_are_distinct():
    text = 'Engine::configure() 함수는 작업 스레드에서 호출되며 성공 시 0을 반환하고 실패 시 오류를 반환합니다.'
    assert similar(text, text.replace('Engine::configure()', 'configure'))
    assert not similar(text, text.replace('Engine::configure()', 'Device::configure()'))


def test_prose_field_owners_distinguish_real_public_frame_context_claims():
    left = '`IPAFrameContext` 구조체의 `lsc` 필드는 `ipa::lsc::FrameContext` 타입으로 선언되어 있으며 프레임별 알고리즘 처리 상태를 보관합니다.'
    right = '`IPAContext` 구조체의 `frameContexts` 필드는 `FCQueue<IPAFrameContext>` 타입으로 선언되어 있으며 프레임별 알고리즘 처리 상태를 보관합니다.'
    assert not similar(left, right)
    text = '`Owner` 구조체의 `field` 필드는 정수 값을 유지하고 요청 처리 중 콜백에서 갱신됩니다.'
    assert similar(text, text.replace('`Owner` 구조체의 `field` 필드는', '`Owner.field`는'))
    assert similar(text, text.replace('`Owner` 구조체의 `field` 필드는', '`ns::Owner.field`는'))


def test_implementer_subject_preserves_distinct_function_contracts():
    configure = '`PipelineHandler::configure()`는 `CameraManager` 스레드에서 호출되며 성공하면 0을, 실패하면 음수 오류를 반환해야 합니다.'
    queue = '`PipelineHandler::queueRequestDevice()`의 구현자는 성공하면 0을, 실패하면 음수 오류를 반환해야 합니다.'
    assert not similar(configure, queue)
    assert similar(queue, queue.replace('의 구현자는', ' 함수는'))
    assert similar(queue, queue.replace('PipelineHandler::queueRequestDevice', 'queueRequestDevice'))


@pytest.mark.parametrize('left,right', [
    ('Worker::run() 함수는 state.ready 가 false 이면 대기 중인 요청을 즉시 반환합니다.',
     'Worker::run() 함수는 state.ready 가 true 이면 대기 중인 요청을 즉시 반환합니다.'),
    ('Worker::run() 함수는 state.ready == false 이면 대기 중인 요청을 즉시 반환합니다.',
     'Worker::run() 함수는 state.ready != false 이면 대기 중인 요청을 즉시 반환합니다.'),
    ('Worker::run() 함수는 요청에 필요한 버퍼가 없으면 -EINVAL 오류를 반환합니다.',
     'Worker::run() 함수는 요청에 필요한 버퍼가 없으면 -ENOMEM 오류를 반환합니다.'),
])
def test_explicit_predicate_values_and_return_codes_remain_distinct(left, right):
    assert not similar(left, right)


def test_equivalent_member_predicate_spelling_stays_a_duplicate():
    text = 'Worker::run() 함수는 state.ready 가 true 이면 대기 중인 요청을 즉시 반환합니다.'
    assert similar(text, text.replace('state.ready 가 true', 'state->ready is true'))


def test_quote_difference_alone_does_not_exempt_same_guard_or_mixed_claims():
    text = 'Worker::run() 함수는 요청이 준비되지 않으면 대기 중인 모든 요청을 즉시 반환합니다.'
    model = _model(**{'t/x': 'same-excerpt'})
    answers = {'t': [dict(text=text, quote='if (!request.ready()) { return; }', evidence=['x']),
                     dict(text=text, quote='if ( !request.ready() ) { log(); return; }', evidence=['x'])]}
    assert len(statement_findings(model, 's', answers)) == 1
    numeric = 'Worker::run() 함수는 요청의 처리 결과가 음수이면 대기 중인 요청을 즉시 반환합니다.'
    answers['t'] = [dict(text=numeric, quote='if (count < 0) { return; }', evidence=['x']),
                    dict(text=numeric, quote='if (0 > count) { return; }', evidence=['x'])]
    assert len(statement_findings(model, 's', answers)) == 1
    # Each sentence contains another repeated clause. A different selected
    # predicate must not exempt this entire mixed claim from review.
    mixed = text + ' 요청이 취소되면 완료 통지를 전송합니다.'
    answers['t'] = [dict(text=mixed, quote='if (!ready) { return; }', evidence=['x']),
                    dict(text=mixed, quote='if (cancelled) { complete(); }', evidence=['x'])]
    assert len(statement_findings(model, 's', answers)) == 1


def test_default_duplicate_threshold_and_minimum_are_unchanged():
    from sdd.duplicates import MINIMUM_SHARED, SIMILARITY
    assert SIMILARITY == .7 and MINIMUM_SHARED == 6


# Genuine duplicates and mixed claims remain review candidates.
REMAINING_CANDIDATES = [('`IPAModule::createInterface()` 함수는 모듈이 로드되지 않았거나 유효하지 않은 경우 `nullptr`를 반환하며, 성공 시 인터페이스 인스턴스를 '
  '생성합니다.',
  '`IPAModule::createInterface` 함수는 모듈이 유효하지 않거나 로드되지 않은 경우 `nullptr`를 반환합니다.'),
 ('`PipelineHandler::doQueueRequest` 함수 내부에서 요청의 취소 상태를 확인하는 위치는 `request->_d()->cancelled_` '
  '조건문입니다. 이 식이 참이면 요청을 즉시 완료하고 함수를 종료합니다.',
  '`PipelineHandler::doQueueRequest` 함수 내부에서 `request->_d()->cancelled_` 조건이 참일 경우, 해당 요청을 즉시 완료 '
  '처리하기 위해 `completeRequest(request)` 함수를 호출합니다.'),
 ('`generateConfiguration` 함수는 임의의 스레드에서 호출할 수 있으며, 이 함수는 반드시 스레드 안전합니다.',
  '`PipelineHandler::generateConfiguration()` 함수는 어떤 스레드에서든 호출될 수 있으며, 반드시 스레드 안전성을 보장해야 합니다.'),
 ('파이프라인 핸들러는 요청의 버퍼 부분을 완료했음을 애플리케이션에 통지하고 요청 내부의 버퍼 추적을 업데이트하기 위해 `completeBuffer` 함수를 호출해야 합니다.',
  '`PipelineHandler::completeBuffer` 함수는 파이프라인 핸들러에 의해 호출되어 요청의 버퍼 부분을 완료하는 신호를 보내고, 애플리케이션에게 버퍼 '
  '완료를 알리며 요청 내부의 버퍼 추적을 갱신합니다.'),
 ('`Camera::createRequest` 함수는 애플리케이션이 버퍼와 매개변수로 채우고 촬영을 대기할 수 있는 빈 요청 객체를 생성하여 호출자에게 반환합니다.',
  '`Camera::createRequest` 함수는 요청 객체를 생성하여 호출자에게 반환하며, 이 반환된 요청의 소유권은 호출자에게 전달됩니다.'),
 ('`Request::addBuffer` 함수에 전달하는 버퍼는 요청 완료 콜백이 호출될 때까지 유효해야 합니다.',
  '`Request::addBuffer` 함수는 요청에 스트림과 연결된 `FrameBuffer` 참조를 저장하며, 호출자는 해당 버퍼가 요청 완료 콜백이 호출될 때까지 '
  '유효하도록 유지해야 합니다.'),
 ('`Camera::createRequest` 함수는 요청 객체를 생성하여 호출자에게 반환하며, 이 반환된 요청의 소유권은 호출자에게 전달됩니다.',
  '`Camera::createRequest()` 함수는 카메라가 `Configured` 또는 `Running` 상태일 때 호출할 수 있으며, 이 함수는 스레드 안전합니다. '
  '반환된 요청 객체의 소유권은 호출자에게 넘어가므로, 호출자는 해당 요청을 삭제하거나 상태를 초기화한 후 재사용해야 합니다.'),
 ('`queueRequest` 함수를 호출하기 전에 호출자는 요청에 최소 하나의 캡처 버퍼를 채워야 합니다.',
  '`Camera::queueRequest()` 함수는 카메라가 `Running` 상태일 때만 호출할 수 있으며, 이 함수도 스레드 안전합니다. 요청에 최소 하나의 캡처 '
  '버퍼가 포함되어 있어야 하며, 버퍼가 없거나 요청이 유효하지 않으면 큐잉이 거부됩니다.'),
 ('`start` 함수는 카메라가 `Configured` 상태일 때만 호출할 수 있습니다.',
  '`Camera::start()` 함수는 카메라가 `Configured` 상태일 때 호출되며, 다른 상태 변경 함수와 동기화되어야 합니다. 성공 시 0을 반환하고 실패 시 '
  '음수 오류 코드를 반환합니다.'),
 ('createIPA() 함수는 module() 으로 찾은 모듈이 없으면 nullptr 를 반환하고, 프록시 생성 시 서명이 유효하지 않으면 Isolated 실행 방식을 '
  '선택합니다.',
  '서명이 유효하지 않으면 createIPA() 는 Isolated 실행 방식을 선택하고, 프록시 생성이 실패하면 nullptr 를 반환합니다.'),
 ('`IPAModule::load()` 함수는 모듈을 로드하거나 이미 로드된 경우에만 성공하며, 유효하지 않은 모듈이나 이미 로드된 상태에서는 `false`를 반환합니다.',
  '`IPAModule::load` 함수는 유효하지 않은 모듈이거나 이미 로드된 경우를 처리하여 `false`를 반환하며, 공유 객체를 열지 못하거나 심볼을 찾을 수 없으면 '
  '에러 로그를 출력하고 `dlHandle_`를 초기화한 뒤 `false`를 반환합니다.')]


@pytest.mark.parametrize('left,right', REMAINING_CANDIDATES)
def test_candidates_without_source_proof_stay_subject_to_review(left, right):
    model = _model(**{'t/x': 'same-excerpt'})
    assert len(statement_findings(model, 's', {'t': [_statement(left, 'x'), _statement(right, 'x')]})) == 1


# Exact public source excerpts: novelty is tested with real quoted contracts.
NOVELTY_SOURCES = {'9f251ecf5ba569606e9753d3619b88e1aef5a4ce15f816ae97efd283e34b823b': '\\brief Create a request '
                                                                     'object for the camera\n'
                                                                     ' * \\param[in] cookie Opaque '
                                                                     'cookie for application use\n'
                                                                     ' *\n'
                                                                     ' * This function creates an '
                                                                     'empty request for the '
                                                                     'application to fill with\n'
                                                                     ' * buffers and parameters, '
                                                                     'and queue for capture.\n'
                                                                     ' *\n'
                                                                     ' * The \\a cookie is stored '
                                                                     'in the request and is '
                                                                     'accessible through the\n'
                                                                     ' * Request::cookie() '
                                                                     'function at any time. It is '
                                                                     'typically used by '
                                                                     'applications\n'
                                                                     ' * to map the request to an '
                                                                     'external resource in the '
                                                                     'request completion\n'
                                                                     ' * handler, and is '
                                                                     'completely opaque to '
                                                                     'libcamera.\n'
                                                                     ' *\n'
                                                                     ' * The ownership of the '
                                                                     'returned request is passed '
                                                                     'to the caller, which is\n'
                                                                     ' * responsible for deleting '
                                                                     'it. The request may be '
                                                                     'deleted in the completion\n'
                                                                     ' * handler, or reused after '
                                                                     'resetting its state with '
                                                                     'Request::reuse().\n'
                                                                     ' *\n'
                                                                     ' * \\context This function '
                                                                     'is \\threadsafe. It may only '
                                                                     'be called when the camera\n'
                                                                     ' * is in the Configured or '
                                                                     'Running state as defined in '
                                                                     '\\ref camera_operation.\n'
                                                                     ' *\n'
                                                                     ' * \\return A pointer to the '
                                                                     'newly created request, or '
                                                                     'nullptr on error\n'
                                                                     ' */\n'
                                                                     'std::unique_ptr<Request> '
                                                                     'Camera::createRequest(uint64_t '
                                                                     'cookie)',
 '65cd8b0501b7f6545dd10eaaec4a4fe46c52a096a3bbd94ea6b4813e4a670876': '\\brief Add a FrameBuffer '
                                                                     'with its associated Stream '
                                                                     'to the Request\n'
                                                                     ' * \\param[in] stream The '
                                                                     'stream the buffer belongs '
                                                                     'to\n'
                                                                     ' * \\param[in] buffer The '
                                                                     'FrameBuffer to add to the '
                                                                     'request\n'
                                                                     ' * \\param[in] fence The '
                                                                     'optional fence\n'
                                                                     ' *\n'
                                                                     ' * A reference to the buffer '
                                                                     'is stored in the request. '
                                                                     'The caller is responsible\n'
                                                                     ' * for ensuring that the '
                                                                     'buffer will remain valid '
                                                                     'until the request complete\n'
                                                                     ' * callback is called.\n'
                                                                     ' *\n'
                                                                     ' * A request can only '
                                                                     'contain one buffer per '
                                                                     'stream. If a buffer has '
                                                                     'already\n'
                                                                     ' * been added to the request '
                                                                     'for the same stream, this '
                                                                     'function returns -EEXIST.\n'
                                                                     ' *\n'
                                                                     ' * A Fence can be optionally '
                                                                     'associated with the \\a '
                                                                     'buffer.\n'
                                                                     ' *\n'
                                                                     ' * When a valid Fence is '
                                                                     'provided to this function, '
                                                                     '\\a fence is moved to \\a\n'
                                                                     ' * buffer and this Request '
                                                                     'will only be queued to the '
                                                                     'device once the\n'
                                                                     ' * fences of all its buffers '
                                                                     'have been correctly '
                                                                     'signalled. Ownership of the\n'
                                                                     ' * fence will only be taken '
                                                                     'in case of success, '
                                                                     'otherwise the fence will\n'
                                                                     ' * be left unmodified.\n'
                                                                     ' *\n'
                                                                     ' * If the \\a fence '
                                                                     'associated with \\a buffer '
                                                                     "isn't signalled, the request "
                                                                     'will\n'
                                                                     ' * fail after a timeout. The '
                                                                     'buffer will still contain '
                                                                     'the fence, which\n'
                                                                     ' * applications must '
                                                                     'retrieve with '
                                                                     'FrameBuffer::releaseFence() '
                                                                     'before the buffer\n'
                                                                     ' * can be reused in another '
                                                                     'request. Attempting to add a '
                                                                     'buffer that still\n'
                                                                     ' * contains a fence to a '
                                                                     'request will result in this '
                                                                     'function returning -EEXIST.\n'
                                                                     ' *\n'
                                                                     ' * \\sa '
                                                                     'FrameBuffer::releaseFence()\n'
                                                                     ' *\n'
                                                                     ' * \\return 0 on success or '
                                                                     'a negative error code '
                                                                     'otherwise\n'
                                                                     ' * \\retval -EEXIST The '
                                                                     'request already contains a '
                                                                     'buffer for the stream\n'
                                                                     ' *  or the buffer still '
                                                                     'references a fence\n'
                                                                     ' * \\retval -EINVAL The '
                                                                     'buffer does not reference a '
                                                                     'valid Stream\n'
                                                                     ' */\n'
                                                                     'int Request::addBuffer(const '
                                                                     'Stream *stream, FrameBuffer '
                                                                     '*buffer,',
 '96db61baeb32065c966b20942f97518ddbd3a43b36b64e8083eb29a90ecb7f4b': '\\brief Queue a request to '
                                                                     'the camera\n'
                                                                     ' * \\param[in] request The '
                                                                     'request to queue to the '
                                                                     'camera\n'
                                                                     ' *\n'
                                                                     ' * This function queues a '
                                                                     '\\a request to the camera '
                                                                     'for capture.\n'
                                                                     ' *\n'
                                                                     ' * After allocating the '
                                                                     'request with '
                                                                     'createRequest(), the '
                                                                     'application shall\n'
                                                                     ' * fill it with at least one '
                                                                     'capture buffer before '
                                                                     'queuing it. Requests that\n'
                                                                     ' * contain no buffers are '
                                                                     'invalid and are rejected '
                                                                     'without being queued.\n'
                                                                     ' *\n'
                                                                     ' * Once the request has been '
                                                                     'queued, the camera will '
                                                                     'notify its completion\n'
                                                                     ' * through the \\ref '
                                                                     'requestCompleted signal.\n'
                                                                     ' *\n'
                                                                     ' * \\context This function '
                                                                     'is \\threadsafe. It may only '
                                                                     'be called when the camera\n'
                                                                     ' * is in the Running state '
                                                                     'as defined in \\ref '
                                                                     'camera_operation.\n'
                                                                     ' *\n'
                                                                     ' * \\return 0 on success or '
                                                                     'a negative error code '
                                                                     'otherwise\n'
                                                                     ' * \\retval -ENODEV The '
                                                                     'camera has been disconnected '
                                                                     'from the system\n'
                                                                     ' * \\retval -EACCES The '
                                                                     'camera is not running so '
                                                                     "requests can't be queued\n"
                                                                     ' * \\retval -EXDEV The '
                                                                     'request does not belong to '
                                                                     'this camera\n'
                                                                     ' * \\retval -EINVAL The '
                                                                     'request is invalid\n'
                                                                     ' * \\retval -ENOMEM No '
                                                                     'buffer memory was available '
                                                                     'to handle the request\n'
                                                                     ' */\n'
                                                                     'int '
                                                                     'Camera::queueRequest(Request '
                                                                     '*request)\n'
                                                                     '{\n'
                                                                     '\tPrivate *const d = _d();\n'
                                                                     '\n'
                                                                     '\tint ret = '
                                                                     'd->isAccessAllowed(Private::CameraRunning);\n'
                                                                     '\tif (ret < 0)\n'
                                                                     '\t\treturn ret;\n'
                                                                     '\n'
                                                                     '\t/* Requests can only be '
                                                                     'queued to the camera that '
                                                                     'created them. */\n'
                                                                     '\tif '
                                                                     '(request->_d()->camera() != '
                                                                     'this) {\n'
                                                                     '\t\tLOG(Camera, Error) << '
                                                                     '"Request was not created by '
                                                                     'this camera";\n'
                                                                     '\t\treturn -EXDEV;\n'
                                                                     '\t}\n'
                                                                     '\n'
                                                                     '\tif (request->status() != '
                                                                     'Request::RequestPending) {\n'
                                                                     '\t\tLOG(Camera, Error) << '
                                                                     'request->toString() << " is '
                                                                     'not valid";\n'
                                                                     '\t\treturn -EINVAL;\n'
                                                                     '\t}\n'
                                                                     '\n'
                                                                     '\t/* Make sure the Request '
                                                                     'has a valid control list. '
                                                                     '*/\n'
                                                                     '\tif '
                                                                     '(request->controls().infoMap() '
                                                                     '!= &controls()) {\n'
                                                                     '\t\tLOG(Camera, Error) << '
                                                                     '"Overwriting '
                                                                     'Request::controls() is not '
                                                                     'allowed";\n'
                                                                     '\t\treturn -EINVAL;\n'
                                                                     '\t}\n'
                                                                     '\n'
                                                                     '\t/*\n'
                                                                     '\t * The camera state may '
                                                                     'change until the end of the '
                                                                     'function. No locking\n'
                                                                     '\t * is however needed as '
                                                                     'PipelineHandler::queueRequest() '
                                                                     'will handle\n'
                                                                     '\t * this.\n'
                                                                     '\t */\n'
                                                                     '\n'
                                                                     '\tif '
                                                                     '(request->buffers().empty()) '
                                                                     '{\n'
                                                                     '\t\tLOG(Camera, Error) << '
                                                                     '"Request contains no '
                                                                     'buffers";\n'
                                                                     '\t\treturn -EINVAL;\n'
                                                                     '\t}\n'
                                                                     '\n'
                                                                     '\tfor (const auto &[stream, '
                                                                     'buffer] : '
                                                                     'request->buffers()) {\n'
                                                                     '\t\tif '
                                                                     '(d->activeStreams_.find(stream) '
                                                                     '== d->activeStreams_.end()) '
                                                                     '{\n'
                                                                     '\t\t\tLOG(Camera, Error) << '
                                                                     '"Invalid request";\n'
                                                                     '\t\t\treturn -EINVAL;\n'
                                                                     '\t\t}\n'
                                                                     '\t}\n'
                                                                     '\n'
                                                                     '\t/* Pre-process AeEnable. '
                                                                     '*/\n'
                                                                     '\t'
                                                                     'patchControlList(request->controls());\n'
                                                                     '\n'
                                                                     '\t'
                                                                     'd->pipe_->invokeMethod(&PipelineHandler::queueRequest,\n'
                                                                     '\t\t\t       '
                                                                     'ConnectionTypeQueued, '
                                                                     'request);\n'
                                                                     '\n'
                                                                     '\treturn 0;\n'
                                                                     '}\n'
                                                                     '\n'
                                                                     '/**\n'
                                                                     ' * \\brief Start capture '
                                                                     'from camera',
 'e0abda64dc6b1bdd78d1326c8dd8651e842c03181dcf28e3b8b7eac1a4c70fcf': '\\brief Start capture from '
                                                                     'camera\n'
                                                                     ' * \\param[in] controls '
                                                                     'Controls to be applied '
                                                                     'before starting the Camera\n'
                                                                     ' *\n'
                                                                     ' * Start the camera capture '
                                                                     'session, optionally '
                                                                     'providing a list of controls '
                                                                     'to\n'
                                                                     ' * apply before starting. '
                                                                     'Once the camera is started '
                                                                     'the application can queue\n'
                                                                     ' * requests to the camera to '
                                                                     'process and return to the '
                                                                     'application until the\n'
                                                                     ' * capture session is '
                                                                     'terminated with \\a stop().\n'
                                                                     ' *\n'
                                                                     ' * \\context This function '
                                                                     'may only be called when the '
                                                                     'camera is in the\n'
                                                                     ' * Configured state as '
                                                                     'defined in \\ref '
                                                                     'camera_operation, and shall '
                                                                     'be\n'
                                                                     ' * synchronized by the '
                                                                     'caller with other functions '
                                                                     'that affect the camera\n'
                                                                     ' * state.\n'
                                                                     ' *\n'
                                                                     ' * \\return 0 on success or '
                                                                     'a negative error code '
                                                                     'otherwise\n'
                                                                     ' * \\retval -ENODEV The '
                                                                     'camera has been disconnected '
                                                                     'from the system\n'
                                                                     ' * \\retval -EACCES The '
                                                                     'camera is not in a state '
                                                                     'where it can be started\n'
                                                                     ' */\n'
                                                                     'int Camera::start(const '
                                                                     'ControlList *controls)',
 'e0bd5192ea24a8b39d3df7b7b93c8b17614663a0144f6dd0741d410fa321d458': 'template<typename T>\n'
                                                                     '\tstd::unique_ptr<T> '
                                                                     'createIPA(const char *name, '
                                                                     'uint32_t minVersion,\n'
                                                                     '\t\t\t\t     uint32_t '
                                                                     'maxVersion)\n'
                                                                     '\t{\n'
                                                                     '\t\tIPAModule *m = '
                                                                     'module(name, minVersion, '
                                                                     'maxVersion);\n'
                                                                     '\t\tif (!m)\n'
                                                                     '\t\t\treturn nullptr;\n'
                                                                     '\n'
                                                                     '\t\tauto proxy = [&]() -> '
                                                                     'std::unique_ptr<T> {\n'
                                                                     '\t\t\tif '
                                                                     '(isSignatureValid(m))\n'
                                                                     '\t\t\t\treturn '
                                                                     'std::make_unique<typename '
                                                                     'T::Threaded>(m, cm_);\n'
                                                                     '\t\t\telse\n'
                                                                     '\t\t\t\treturn '
                                                                     'std::make_unique<typename '
                                                                     'T::Isolated>(m, cm_);\n'
                                                                     '\t\t}();\n'
                                                                     '\n'
                                                                     '\t\tif (!proxy->isValid()) '
                                                                     '{\n'
                                                                     '\t\t\tLOG(IPAManager, Error) '
                                                                     '<< "Failed to load proxy";\n'
                                                                     '\t\t\treturn nullptr;\n'
                                                                     '\t\t}\n'
                                                                     '\n'
                                                                     '\t\treturn proxy;\n'
                                                                     '\t}\n'
                                                                     '\n'
                                                                     '#if HAVE_IPA_PUBKEY',
 'a1e13344bfc27e191c6c24c682f3a088446d42c99b9497c6e831ab1b97b55619': '\\brief Load the IPA '
                                                                     'implementation factory from '
                                                                     'the shared object\n'
                                                                     ' *\n'
                                                                     ' * The IPA module shared '
                                                                     'object implements an '
                                                                     'IPAInterface object to be '
                                                                     'used\n'
                                                                     ' * by pipeline handlers. '
                                                                     'This function loads the '
                                                                     'factory function from the\n'
                                                                     ' * shared object. Later, '
                                                                     'createInterface() can be '
                                                                     'called to instantiate the\n'
                                                                     ' * IPAInterface.\n'
                                                                     ' *\n'
                                                                     ' * This function only needs '
                                                                     'to be called successfully '
                                                                     'once, after which\n'
                                                                     ' * createInterface() can be '
                                                                     'called as many times as '
                                                                     'IPAInterface instances are\n'
                                                                     ' * needed.\n'
                                                                     ' *\n'
                                                                     ' * Calling this function on '
                                                                     'an invalid module (as '
                                                                     'returned by isValid()) is\n'
                                                                     ' * an error.\n'
                                                                     ' *\n'
                                                                     ' * \\return True if load was '
                                                                     'successful, or already '
                                                                     'loaded, and false otherwise\n'
                                                                     ' */\n'
                                                                     'bool IPAModule::load()\n'
                                                                     '{\n'
                                                                     '\tif (!valid_)\n'
                                                                     '\t\treturn false;\n'
                                                                     '\n'
                                                                     '\tif (loaded_)\n'
                                                                     '\t\treturn true;\n'
                                                                     '\n'
                                                                     '\tdlHandle_ = '
                                                                     'dlopen(libPath_.c_str(), '
                                                                     'RTLD_LAZY);\n'
                                                                     '\tif (!dlHandle_) {\n'
                                                                     '\t\tLOG(IPAModule, Error)\n'
                                                                     '\t\t\t<< "Failed to open IPA '
                                                                     'module shared object: "\n'
                                                                     '\t\t\t<< dlerror();\n'
                                                                     '\t\treturn false;\n'
                                                                     '\t}\n'
                                                                     '\n'
                                                                     '\tvoid *symbol = '
                                                                     'dlsym(dlHandle_, '
                                                                     '"ipaCreate");\n'
                                                                     '\tif (!symbol) {\n'
                                                                     '\t\tLOG(IPAModule, Error)\n'
                                                                     '\t\t\t<< "Failed to load '
                                                                     'ipaCreate() from IPA module '
                                                                     'shared object: "\n'
                                                                     '\t\t\t<< dlerror();\n'
                                                                     '\t\tdlclose(dlHandle_);\n'
                                                                     '\t\tdlHandle_ = nullptr;\n'
                                                                     '\t\treturn false;\n'
                                                                     '\t}\n'
                                                                     '\n'
                                                                     '\tipaCreate_ = '
                                                                     'reinterpret_cast<IPAIntfFactory>(symbol);\n'
                                                                     '\n'
                                                                     '\tloaded_ = true;\n'
                                                                     '\n'
                                                                     '\treturn true;\n'
                                                                     '}\n'
                                                                     '\n'
                                                                     '/**\n'
                                                                     ' * \\brief Instantiate an '
                                                                     'IPA interface\n'
                                                                     ' *\n'
                                                                     ' * After loading the IPA '
                                                                     'module with load(), this '
                                                                     'function creates an '
                                                                     'instance\n'
                                                                     ' * of the IPA module '
                                                                     'interface.\n'
                                                                     ' *\n'
                                                                     ' * Calling this function on '
                                                                     'a module that has not yet '
                                                                     'been loaded, or an\n'
                                                                     ' * invalid module (as '
                                                                     'returned by load() and '
                                                                     'isValid(), respectively) is\n'
                                                                     ' * an error.\n'
                                                                     ' *\n'
                                                                     ' * \\return The IPA '
                                                                     'interface on success, or '
                                                                     'nullptr on error\n'
                                                                     ' */\n'
                                                                     'IPAInterface '
                                                                     '*IPAModule::createInterface()\n'
                                                                     '{\n'
                                                                     '\tif (!valid_ || !loaded_)\n'
                                                                     '\t\treturn nullptr;\n'
                                                                     '\n'
                                                                     '\treturn ipaCreate_();\n'
                                                                     '}\n'
                                                                     '\n'
                                                                     '/**\n'
                                                                     ' * \\brief Verify if the IPA '
                                                                     'module matches',
 '1ebc4d56b99218bfb196cf7548aa7167a251392ddb7bf53af9ef4963cc24636b': 'if '
                                                                     '(request->_d()->cancelled_) '
                                                                     '{\n'
                                                                     '\t\t'
                                                                     'completeRequest(request);\n'
                                                                     '\t\treturn;',
 'dcef1582ffd11183a0765511757597c9619de8b015f123e92622a389a4bebd26': '\\context This function may '
                                                                     'be called from any thread '
                                                                     'and shall be\n'
                                                                     ' * \\threadsafe.',
 '60f0e467f8ae13c4ddb878bc507741645fdc3e4ac08fd4975645667c0973c7f7': 'This function shall be '
                                                                     'called by pipeline handlers '
                                                                     'to signal completion of\n'
                                                                     ' * the \\a buffer part of '
                                                                     'the \\a request. It notifies '
                                                                     'applications of buffer\n'
                                                                     ' * completion and updates '
                                                                     "the request's internal "
                                                                     'buffer tracking.'}

SOURCE_CANDIDATES = [('`Camera::createRequest` 함수는 애플리케이션이 버퍼와 매개변수로 채우고 촬영을 대기할 수 있는 빈 요청 객체를 생성하여 호출자에게 반환합니다.',
  '`Camera::createRequest` 함수는 요청 객체를 생성하여 호출자에게 반환하며, 이 반환된 요청의 소유권은 호출자에게 전달됩니다.',
  '\\brief Create a request object for the camera\n'
  ' * \\param[in] cookie Opaque cookie for application use\n'
  ' *\n'
  ' * This function creates an empty request for the application to fill with\n'
  ' * buffers and parameters, and queue for capture.\n'
  ' *\n'
  ' * The \\a cookie is stored in the request and is accessible through the\n'
  ' * Request::cookie() function at any time. It is typically used by applications\n'
  ' * to map the request to an external resource in the request completion\n'
  ' * handler, and is completely opaque to libcamera.\n'
  ' *\n'
  ' * The ownership of the returned request is passed to the caller, which is\n'
  ' * responsible for deleting it. The request may be deleted in the completion\n'
  ' * handler, or reused after resetting its state with Request::reuse().\n'
  ' *\n'
  ' * \\context This function is \\threadsafe. It may only be called when the camera\n'
  ' * is in the Configured or Running state as defined in \\ref camera_operation.\n'
  ' *\n'
  ' * \\return A pointer to the newly created request, or nullptr on error\n'
  ' */\n'
  'std::unique_ptr<Request> Camera::createRequest(uint64_t cookie)',
  '\\brief Create a request object for the camera\n'
  ' * \\param[in] cookie Opaque cookie for application use\n'
  ' *\n'
  ' * This function creates an empty request for the application to fill with\n'
  ' * buffers and parameters, and queue for capture.\n'
  ' *\n'
  ' * The \\a cookie is stored in the request and is accessible through the\n'
  ' * Request::cookie() function at any time. It is typically used by applications\n'
  ' * to map the request to an external resource in the request completion\n'
  ' * handler, and is completely opaque to libcamera.\n'
  ' *\n'
  ' * The ownership of the returned request is passed to the caller, which is\n'
  ' * responsible for deleting it. The request may be deleted in the completion\n'
  ' * handler, or reused after resetting its state with Request::reuse().\n'
  ' *\n'
  ' * \\context This function is \\threadsafe. It may only be called when the camera\n'
  ' * is in the Configured or Running state as defined in \\ref camera_operation.\n'
  ' *\n'
  ' * \\return A pointer to the newly created request, or nullptr on error\n'
  ' */\n'
  'std::unique_ptr<Request> Camera::createRequest(uint64_t cookie)',
  '9f251ecf5ba569606e9753d3619b88e1aef5a4ce15f816ae97efd283e34b823b',
  ['contract:ownership-transfer']),
 ('`Request::addBuffer` 함수에 전달하는 버퍼는 요청 완료 콜백이 호출될 때까지 유효해야 합니다.',
  '`Request::addBuffer` 함수는 요청에 스트림과 연결된 `FrameBuffer` 참조를 저장하며, 호출자는 해당 버퍼가 요청 완료 콜백이 호출될 때까지 '
  '유효하도록 유지해야 합니다.',
  '\\brief Add a FrameBuffer with its associated Stream to the Request\n'
  ' * \\param[in] stream The stream the buffer belongs to\n'
  ' * \\param[in] buffer The FrameBuffer to add to the request\n'
  ' * \\param[in] fence The optional fence\n'
  ' *\n'
  ' * A reference to the buffer is stored in the request. The caller is responsible\n'
  ' * for ensuring that the buffer will remain valid until the request complete\n'
  ' * callback is called.\n'
  ' *\n'
  ' * A request can only contain one buffer per stream. If a buffer has already\n'
  ' * been added to the request for the same stream, this function returns -EEXIST.\n'
  ' *\n'
  ' * A Fence can be optionally associated with the \\a buffer.\n'
  ' *\n'
  ' * When a valid Fence is provided to this function, \\a fence is moved to \\a\n'
  ' * buffer and this Request will only be queued to the device once the\n'
  ' * fences of all its buffers have been correctly signalled. Ownership of the\n'
  ' * fence will only be taken in case of success, otherwise the fence will\n'
  ' * be left unmodified.\n'
  ' *\n'
  " * If the \\a fence associated with \\a buffer isn't signalled, the request will\n"
  ' * fail after a timeout. The buffer will still contain the fence, which\n'
  ' * applications must retrieve with FrameBuffer::releaseFence() before the buffer\n'
  ' * can be reused in another request. Attempting to add a buffer that still\n'
  ' * contains a fence to a request will result in this function returning -EEXIST.\n'
  ' *\n'
  ' * \\sa FrameBuffer::releaseFence()\n'
  ' *\n'
  ' * \\return 0 on success or a negative error code otherwise\n'
  ' * \\retval -EEXIST The request already contains a buffer for the stream\n'
  ' *  or the buffer still references a fence\n'
  ' * \\retval -EINVAL The buffer does not reference a valid Stream\n'
  ' */\n'
  'int Request::addBuffer(const Stream *stream, FrameBuffer *buffer,',
  '\\brief Add a FrameBuffer with its associated Stream to the Request\n'
  ' * \\param[in] stream The stream the buffer belongs to\n'
  ' * \\param[in] buffer The FrameBuffer to add to the request\n'
  ' * \\param[in] fence The optional fence\n'
  ' *\n'
  ' * A reference to the buffer is stored in the request. The caller is responsible\n'
  ' * for ensuring that the buffer will remain valid until the request complete\n'
  ' * callback is called.\n'
  ' *\n'
  ' * A request can only contain one buffer per stream. If a buffer has already\n'
  ' * been added to the request for the same stream, this function returns -EEXIST.\n'
  ' *\n'
  ' * A Fence can be optionally associated with the \\a buffer.\n'
  ' *\n'
  ' * When a valid Fence is provided to this function, \\a fence is moved to \\a\n'
  ' * buffer and this Request will only be queued to the device once the\n'
  ' * fences of all its buffers have been correctly signalled. Ownership of the\n'
  ' * fence will only be taken in case of success, otherwise the fence will\n'
  ' * be left unmodified.\n'
  ' *\n'
  " * If the \\a fence associated with \\a buffer isn't signalled, the request will\n"
  ' * fail after a timeout. The buffer will still contain the fence, which\n'
  ' * applications must retrieve with FrameBuffer::releaseFence() before the buffer\n'
  ' * can be reused in another request. Attempting to add a buffer that still\n'
  ' * contains a fence to a request will result in this function returning -EEXIST.\n'
  ' *\n'
  ' * \\sa FrameBuffer::releaseFence()\n'
  ' *\n'
  ' * \\return 0 on success or a negative error code otherwise\n'
  ' * \\retval -EEXIST The request already contains a buffer for the stream\n'
  ' *  or the buffer still references a fence\n'
  ' * \\retval -EINVAL The buffer does not reference a valid Stream\n'
  ' */\n'
  'int Request::addBuffer(const Stream *stream, FrameBuffer *buffer,',
  '65cd8b0501b7f6545dd10eaaec4a4fe46c52a096a3bbd94ea6b4813e4a670876',
  ['contract:reference-storage']),
 ('`Camera::createRequest` 함수는 요청 객체를 생성하여 호출자에게 반환하며, 이 반환된 요청의 소유권은 호출자에게 전달됩니다.',
  '`Camera::createRequest()` 함수는 카메라가 `Configured` 또는 `Running` 상태일 때 호출할 수 있으며, 이 함수는 스레드 안전합니다. '
  '반환된 요청 객체의 소유권은 호출자에게 넘어가므로, 호출자는 해당 요청을 삭제하거나 상태를 초기화한 후 재사용해야 합니다.',
  '\\brief Create a request object for the camera\n'
  ' * \\param[in] cookie Opaque cookie for application use\n'
  ' *\n'
  ' * This function creates an empty request for the application to fill with\n'
  ' * buffers and parameters, and queue for capture.\n'
  ' *\n'
  ' * The \\a cookie is stored in the request and is accessible through the\n'
  ' * Request::cookie() function at any time. It is typically used by applications\n'
  ' * to map the request to an external resource in the request completion\n'
  ' * handler, and is completely opaque to libcamera.\n'
  ' *\n'
  ' * The ownership of the returned request is passed to the caller, which is\n'
  ' * responsible for deleting it. The request may be deleted in the completion\n'
  ' * handler, or reused after resetting its state with Request::reuse().\n'
  ' *\n'
  ' * \\context This function is \\threadsafe. It may only be called when the camera\n'
  ' * is in the Configured or Running state as defined in \\ref camera_operation.\n'
  ' *\n'
  ' * \\return A pointer to the newly created request, or nullptr on error\n'
  ' */\n'
  'std::unique_ptr<Request> Camera::createRequest(uint64_t cookie)',
  '\\brief Create a request object for the camera\n'
  ' * \\param[in] cookie Opaque cookie for application use\n'
  ' *\n'
  ' * This function creates an empty request for the application to fill with\n'
  ' * buffers and parameters, and queue for capture.\n'
  ' *\n'
  ' * The \\a cookie is stored in the request and is accessible through the\n'
  ' * Request::cookie() function at any time. It is typically used by applications\n'
  ' * to map the request to an external resource in the request completion\n'
  ' * handler, and is completely opaque to libcamera.\n'
  ' *\n'
  ' * The ownership of the returned request is passed to the caller, which is\n'
  ' * responsible for deleting it. The request may be deleted in the completion\n'
  ' * handler, or reused after resetting its state with Request::reuse().\n'
  ' *\n'
  ' * \\context This function is \\threadsafe. It may only be called when the camera\n'
  ' * is in the Configured or Running state as defined in \\ref camera_operation.\n'
  ' *\n'
  ' * \\return A pointer to the newly created request, or nullptr on error\n'
  ' */\n'
  'std::unique_ptr<Request> Camera::createRequest(uint64_t cookie)',
  '9f251ecf5ba569606e9753d3619b88e1aef5a4ce15f816ae97efd283e34b823b',
  ['contract:thread-safety']),
 ('`queueRequest` 함수를 호출하기 전에 호출자는 요청에 최소 하나의 캡처 버퍼를 채워야 합니다.',
  '`Camera::queueRequest()` 함수는 카메라가 `Running` 상태일 때만 호출할 수 있으며, 이 함수도 스레드 안전합니다. 요청에 최소 하나의 캡처 '
  '버퍼가 포함되어 있어야 하며, 버퍼가 없거나 요청이 유효하지 않으면 큐잉이 거부됩니다.',
  '\\brief Queue a request to the camera\n'
  ' * \\param[in] request The request to queue to the camera\n'
  ' *\n'
  ' * This function queues a \\a request to the camera for capture.\n'
  ' *\n'
  ' * After allocating the request with createRequest(), the application shall\n'
  ' * fill it with at least one capture buffer before queuing it. Requests that\n'
  ' * contain no buffers are invalid and are rejected without being queued.\n'
  ' *\n'
  ' * Once the request has been queued, the camera will notify its completion\n'
  ' * through the \\ref requestCompleted signal.\n'
  ' *\n'
  ' * \\context This function is \\threadsafe. It may only be called when the camera\n'
  ' * is in the Running state as defined in \\ref camera_operation.\n'
  ' *\n'
  ' * \\return 0 on success or a negative error code otherwise\n'
  ' * \\retval -ENODEV The camera has been disconnected from the system\n'
  " * \\retval -EACCES The camera is not running so requests can't be queued\n"
  ' * \\retval -EXDEV The request does not belong to this camera\n'
  ' * \\retval -EINVAL The request is invalid\n'
  ' * \\retval -ENOMEM No buffer memory was available to handle the request\n'
  ' */\n'
  'int Camera::queueRequest(Request *request)\n'
  '{\n'
  '\tPrivate *const d = _d();',
  '\\brief Queue a request to the camera\n'
  ' * \\param[in] request The request to queue to the camera\n'
  ' *\n'
  ' * This function queues a \\a request to the camera for capture.\n'
  ' *\n'
  ' * After allocating the request with createRequest(), the application shall\n'
  ' * fill it with at least one capture buffer before queuing it. Requests that\n'
  ' * contain no buffers are invalid and are rejected without being queued.\n'
  ' *\n'
  ' * Once the request has been queued, the camera will notify its completion\n'
  ' * through the \\ref requestCompleted signal.\n'
  ' *\n'
  ' * \\context This function is \\threadsafe. It may only be called when the camera\n'
  ' * is in the Running state as defined in \\ref camera_operation.\n'
  ' *\n'
  ' * \\return 0 on success or a negative error code otherwise\n'
  ' * \\retval -ENODEV The camera has been disconnected from the system\n'
  " * \\retval -EACCES The camera is not running so requests can't be queued\n"
  ' * \\retval -EXDEV The request does not belong to this camera\n'
  ' * \\retval -EINVAL The request is invalid\n'
  ' * \\retval -ENOMEM No buffer memory was available to handle the request\n'
  ' */\n'
  'int Camera::queueRequest(Request *request)\n'
  '{\n'
  '\tPrivate *const d = _d();',
  '96db61baeb32065c966b20942f97518ddbd3a43b36b64e8083eb29a90ecb7f4b',
  ['contract:thread-safety']),
 ('`start` 함수는 카메라가 `Configured` 상태일 때만 호출할 수 있습니다.',
  '`Camera::start()` 함수는 카메라가 `Configured` 상태일 때 호출되며, 다른 상태 변경 함수와 동기화되어야 합니다. 성공 시 0을 반환하고 실패 시 '
  '음수 오류 코드를 반환합니다.',
  '\\brief Start capture from camera\n'
  ' * \\param[in] controls Controls to be applied before starting the Camera\n'
  ' *\n'
  ' * Start the camera capture session, optionally providing a list of controls to\n'
  ' * apply before starting. Once the camera is started the application can queue\n'
  ' * requests to the camera to process and return to the application until the\n'
  ' * capture session is terminated with \\a stop().\n'
  ' *\n'
  ' * \\context This function may only be called when the camera is in the\n'
  ' * Configured state as defined in \\ref camera_operation, and shall be\n'
  ' * synchronized by the caller with other functions that affect the camera\n'
  ' * state.\n'
  ' *\n'
  ' * \\return 0 on success or a negative error code otherwise\n'
  ' * \\retval -ENODEV The camera has been disconnected from the system\n'
  ' * \\retval -EACCES The camera is not in a state where it can be started\n'
  ' */\n'
  'int Camera::start(const ControlList *controls)',
  '\\brief Start capture from camera\n'
  ' * \\param[in] controls Controls to be applied before starting the Camera\n'
  ' *\n'
  ' * Start the camera capture session, optionally providing a list of controls to\n'
  ' * apply before starting. Once the camera is started the application can queue\n'
  ' * requests to the camera to process and return to the application until the\n'
  ' * capture session is terminated with \\a stop().\n'
  ' *\n'
  ' * \\context This function may only be called when the camera is in the\n'
  ' * Configured state as defined in \\ref camera_operation, and shall be\n'
  ' * synchronized by the caller with other functions that affect the camera\n'
  ' * state.\n'
  ' *\n'
  ' * \\return 0 on success or a negative error code otherwise\n'
  ' * \\retval -ENODEV The camera has been disconnected from the system\n'
  ' * \\retval -EACCES The camera is not in a state where it can be started\n'
  ' */\n'
  'int Camera::start(const ControlList *controls)',
  'e0abda64dc6b1bdd78d1326c8dd8651e842c03181dcf28e3b8b7eac1a4c70fcf',
  ['contract:caller-synchronization']),
 ('createIPA() 함수는 module() 으로 찾은 모듈이 없으면 nullptr 를 반환하고, 프록시 생성 시 서명이 유효하지 않으면 Isolated 실행 방식을 '
  '선택합니다.',
  '서명이 유효하지 않으면 createIPA() 는 Isolated 실행 방식을 선택하고, 프록시 생성이 실패하면 nullptr 를 반환합니다.',
  'template<typename T>\n'
  '\tstd::unique_ptr<T> createIPA(const char *name, uint32_t minVersion,\n'
  '\t\t\t\t     uint32_t maxVersion)\n'
  '\t{\n'
  '\t\tIPAModule *m = module(name, minVersion, maxVersion);\n'
  '\t\tif (!m)\n'
  '\t\t\treturn nullptr;',
  'if (!proxy->isValid()) {\n'
  '\t\t\tLOG(IPAManager, Error) << "Failed to load proxy";\n'
  '\t\t\treturn nullptr;\n'
  '\t\t}',
  'e0bd5192ea24a8b39d3df7b7b93c8b17614663a0144f6dd0741d410fa321d458',
  ['return-guard:isValid(),proxy']),
 ('`IPAModule::load()` 함수는 모듈을 로드하거나 이미 로드된 경우에만 성공하며, 유효하지 않은 모듈이나 이미 로드된 상태에서는 `false`를 반환합니다.',
  '`IPAModule::load` 함수는 유효하지 않은 모듈이거나 이미 로드된 경우를 처리하여 `false`를 반환하며, 공유 객체를 열지 못하거나 심볼을 찾을 수 없으면 '
  '에러 로그를 출력하고 `dlHandle_`를 초기화한 뒤 `false`를 반환합니다.',
  '\\brief Load the IPA implementation factory from the shared object\n'
  ' *\n'
  ' * The IPA module shared object implements an IPAInterface object to be used\n'
  ' * by pipeline handlers. This function loads the factory function from the\n'
  ' * shared object. Later, createInterface() can be called to instantiate the\n'
  ' * IPAInterface.\n'
  ' *\n'
  ' * This function only needs to be called successfully once, after which\n'
  ' * createInterface() can be called as many times as IPAInterface instances are\n'
  ' * needed.\n'
  ' *\n'
  ' * Calling this function on an invalid module (as returned by isValid()) is\n'
  ' * an error.\n'
  ' *\n'
  ' * \\return True if load was successful, or already loaded, and false otherwise\n'
  ' */\n'
  'bool IPAModule::load()\n'
  '{\n'
  '\tif (!valid_)\n'
  '\t\treturn false;',
  'dlHandle_ = dlopen(libPath_.c_str(), RTLD_LAZY);\n'
  '\tif (!dlHandle_) {\n'
  '\t\tLOG(IPAModule, Error)\n'
  '\t\t\t<< "Failed to open IPA module shared object: "\n'
  '\t\t\t<< dlerror();\n'
  '\t\treturn false;\n'
  '\t}',
  'a1e13344bfc27e191c6c24c682f3a088446d42c99b9497c6e831ab1b97b55619',
  ['member-write:dlHandle_']),
 ('`IPAModule::createInterface()` 함수는 모듈이 로드되지 않았거나 유효하지 않은 경우 `nullptr`를 반환하며, 성공 시 인터페이스 인스턴스를 '
  '생성합니다.',
  '`IPAModule::createInterface` 함수는 모듈이 유효하지 않거나 로드되지 않은 경우 `nullptr`를 반환합니다.',
  '/**\n'
  ' * \\brief Instantiate an IPA interface\n'
  ' *\n'
  ' * After loading the IPA module with load(), this function creates an instance\n'
  ' * of the IPA module interface.\n'
  ' *\n'
  ' * Calling this function on a module that has not yet been loaded, or an\n'
  ' * invalid module (as returned by load() and isValid(), respectively) is\n'
  ' * an error.\n'
  ' *\n'
  ' * \\return The IPA interface on success, or nullptr on error\n'
  ' */\n'
  'IPAInterface *IPAModule::createInterface()\n'
  '{\n'
  '\tif (!valid_ || !loaded_)\n'
  '\t\treturn nullptr;',
  '/**\n'
  ' * \\brief Instantiate an IPA interface\n'
  ' *\n'
  ' * After loading the IPA module with load(), this function creates an instance\n'
  ' * of the IPA module interface.\n'
  ' *\n'
  ' * Calling this function on a module that has not yet been loaded, or an\n'
  ' * invalid module (as returned by load() and isValid(), respectively) is\n'
  ' * an error.\n'
  ' *\n'
  ' * \\return The IPA interface on success, or nullptr on error\n'
  ' */\n'
  'IPAInterface *IPAModule::createInterface()\n'
  '{\n'
  '\tif (!valid_ || !loaded_)\n'
  '\t\treturn nullptr;',
  'a1e13344bfc27e191c6c24c682f3a088446d42c99b9497c6e831ab1b97b55619',
  []),
 ('`PipelineHandler::doQueueRequest` 함수 내부에서 요청의 취소 상태를 확인하는 위치는 `request->_d()->cancelled_` '
  '조건문입니다. 이 식이 참이면 요청을 즉시 완료하고 함수를 종료합니다.',
  '`PipelineHandler::doQueueRequest` 함수 내부에서 `request->_d()->cancelled_` 조건이 참일 경우, 해당 요청을 즉시 완료 '
  '처리하기 위해 `completeRequest(request)` 함수를 호출합니다.',
  'if (request->_d()->cancelled_) {\n\t\tcompleteRequest(request);\n\t\treturn;',
  'if (request->_d()->cancelled_) {\n\t\tcompleteRequest(request);\n\t\treturn;',
  '1ebc4d56b99218bfb196cf7548aa7167a251392ddb7bf53af9ef4963cc24636b',
  ['call:completeRequest']),
 ('`generateConfiguration` 함수는 임의의 스레드에서 호출할 수 있으며, 이 함수는 반드시 스레드 안전합니다.',
  '`PipelineHandler::generateConfiguration()` 함수는 어떤 스레드에서든 호출될 수 있으며, 반드시 스레드 안전성을 보장해야 합니다.',
  '\\context This function may be called from any thread and shall be\n * \\threadsafe.',
  '\\context This function may be called from any thread and shall be\n * \\threadsafe.',
  'dcef1582ffd11183a0765511757597c9619de8b015f123e92622a389a4bebd26',
  []),
 ('파이프라인 핸들러는 요청의 버퍼 부분을 완료했음을 애플리케이션에 통지하고 요청 내부의 버퍼 추적을 업데이트하기 위해 `completeBuffer` 함수를 호출해야 합니다.',
  '`PipelineHandler::completeBuffer` 함수는 파이프라인 핸들러에 의해 호출되어 요청의 버퍼 부분을 완료하는 신호를 보내고, 애플리케이션에게 버퍼 '
  '완료를 알리며 요청 내부의 버퍼 추적을 갱신합니다.',
  'This function shall be called by pipeline handlers to signal completion of\n'
  ' * the \\a buffer part of the \\a request. It notifies applications of buffer\n'
  " * completion and updates the request's internal buffer tracking.",
  'This function shall be called by pipeline handlers to signal completion of\n'
  ' * the \\a buffer part of the \\a request. It notifies applications of buffer\n'
  " * completion and updates the request's internal buffer tracking.",
  '60f0e467f8ae13c4ddb878bc507741645fdc3e4ac08fd4975645667c0973c7f7',
  [])]


@pytest.mark.parametrize('left,right,left_quote,right_quote,source_key,features', SOURCE_CANDIDATES)
def test_directional_public_novelty_requires_source_proof(left, right, left_quote, right_quote, source_key, features):
    source = NOVELTY_SOURCES[source_key]
    model = _sourced_model(source)
    answers = {'t': [dict(text=left, quote=left_quote, evidence=['x']),
                     dict(text=right, quote=right_quote, evidence=['x'])]}
    assert bool(statement_findings(model, 's', answers)) is (not bool(features))
    from sdd.duplicates import _novel_features
    assert sorted(_novel_features(model, 's', 't', answers['t'][1], answers['t'][0])) == features


def _sourced_model(source):
    import hashlib
    return SimpleNamespace(evidence={'s/t/x': dict(status='available', text=source,
        sha256=hashlib.sha256(source.encode('utf-8')).hexdigest())})


CALL_SOURCE = 'if (request->cancelled_) { finish(request); return; }'
BASE_CLAIM = 'Worker::run() 함수는 요청을 즉시 완료하고 대기 중인 모든 요청의 처리를 종료합니다.'


def _found_pair(left, right, source=CALL_SOURCE, left_quote=None, right_quote=None):
    model = _sourced_model(source)
    rows = [dict(text=left, quote=source if left_quote is None else left_quote, evidence=['x']),
            dict(text=right, quote=source if right_quote is None else right_quote, evidence=['x'])]
    return statement_findings(model, 's', {'t': rows})


def test_source_backed_call_addition_is_directional_and_aliases_are_not_novel():
    detail = BASE_CLAIM + ' finish(request) 함수를 호출합니다.'
    assert _found_pair(BASE_CLAIM, detail) == []
    assert len(_found_pair(detail, BASE_CLAIM)) == 1
    assert len(_found_pair(detail, detail.replace('finish(request)', 'Worker::finish(request)'))) == 1


@pytest.mark.parametrize('suffix', [
    ' arbitraryEnglishWord', ' ownership threadsafe synchronized',
    ' finish(request)', ' invented(request) 함수를 호출합니다.',
    ' finish(request) 함수를 호출하지 않습니다.',
    ' 소유권은 호출자에게 전달되지 않습니다.',
    ' 이 함수는 스레드 안전하지 않습니다.',
])
def test_arbitrary_or_unsupported_suffix_cannot_waive_a_duplicate(suffix):
    assert len(_found_pair(BASE_CLAIM, BASE_CLAIM + suffix)) == 1


def test_comment_or_declaration_does_not_prove_a_new_call():
    detail = BASE_CLAIM + ' finish(request) 함수를 호출합니다.'
    for source in ('// finish(request);\nreturn;', 'void finish(Request *request);'):
        assert len(_found_pair(BASE_CLAIM, detail, source)) == 1


def test_novelty_requires_source_hash_and_bound_quote():
    from sdd.duplicates import _novel_features
    detail = BASE_CLAIM + ' finish(request) 함수를 호출합니다.'
    earlier = dict(text=BASE_CLAIM, quote=CALL_SOURCE, evidence=['x'])
    later = dict(text=detail, quote=CALL_SOURCE, evidence=['x'])
    model = _sourced_model(CALL_SOURCE)
    model.evidence['s/t/x']['sha256'] = 'damaged'
    assert _novel_features(model, 's', 't', later, earlier) == set()
    model = _sourced_model(CALL_SOURCE)
    later['quote'] = 'a quote absent from the source'
    assert _novel_features(model, 's', 't', later, earlier) == set()


def test_return_guard_novelty_needs_one_return_distinct_condition_and_two_proven_branches():
    module = 'if (!module) { return nullptr; }'
    proxy = 'if (!proxy->isValid()) { return nullptr; }'
    source = module + '\n' + proxy
    before = 'Factory::create() 함수는 모듈이 없으면 nullptr를 반환하고, 서명이 유효하지 않으면 격리 방식을 선택합니다.'
    after = 'Factory::create() 함수는 서명이 유효하지 않으면 격리 방식을 선택하고, 프록시 생성이 실패하면 nullptr를 반환합니다.'
    assert _found_pair(before, after, source, module, proxy) == []
    assert len(_found_pair(before, before, source, module, proxy)) == 1
    assert len(_found_pair(before, before + ' arbitraryEnglishWord', source, module, proxy)) == 1
    assert len(_found_pair(before, before + ' 추가 조건이면 기록합니다.', source, module, proxy)) == 1
    # Multiple explicit returns make an entire mixed paragraph ineligible.
    mixed = after + ' 모듈이 없으면 nullptr를 반환합니다.'
    assert len(_found_pair(before, mixed, source, module, proxy)) == 1
    # A different-looking quote must still be bound to this evidence.
    assert len(_found_pair(before, after, module, module, proxy)) == 1


def test_repeated_sentences_inside_one_statement_are_rejected():
    text = '완료 처리기는 대기 중인 모든 요청의 완료를 알리고 요청 내부의 버퍼 추적을 갱신합니다.'
    model = _model(**{'t/x': 'same-excerpt'})
    found = statement_findings(model, 's', {'t': [_statement(text + ' ' + text, 'x')]})
    assert len(found) == 1
    assert '1번째 설명의 2번째 문장' in found[0] and '같은 설명의 1번째 문장' in found[0]


def test_distinct_member_guards_inside_one_statement_are_preserved():
    first = 'Worker::run() 함수는 state.ready 가 false 이면 대기 중인 모든 요청을 즉시 반환합니다.'
    second = first.replace('false', 'true')
    source = 'if (!state.ready) { return; } if (state.ready) { return; }'
    model = _sourced_model(source)
    row = dict(text=first + ' ' + second, quote=source, evidence=['x'])
    assert statement_findings(model, 's', {'t': [row]}) == []


@pytest.mark.parametrize('call,duplicate', [('finish(request)', False), ('invented(request)', True)])
def test_internal_repetition_preserves_only_source_backed_new_calls(call, duplicate):
    second = BASE_CLAIM.removesuffix('.') + f', {call} 함수를 호출합니다.'
    row = dict(text=BASE_CLAIM + ' ' + second, quote=CALL_SOURCE, evidence=['x'])
    assert bool(statement_findings(_sourced_model(CALL_SOURCE), 's', {'t': [row]})) is duplicate


def test_only_after_also_limits_internal_sentence_rechecks():
    text = '완료 처리기는 대기 중인 모든 요청의 완료를 알리고 요청 내부의 버퍼 추적을 갱신합니다.'
    model = _model(**{'t/x': 'same-excerpt'})
    answers = {'t': [_statement(text + ' ' + text, 'x')]}
    assert statement_findings(model, 's', answers, only_after={'t': 1}) == []


def _assert_proof_cannot_waive(suffix, source, self_paragraph):
    detail = BASE_CLAIM.removesuffix('.') + ', ' + suffix
    model = _sourced_model(source)
    if self_paragraph:
        rows = [dict(text=BASE_CLAIM + ' ' + detail, quote=source, evidence=['x'])]
    else:
        rows = [dict(text=BASE_CLAIM, quote=source, evidence=['x']),
                dict(text=detail, quote=source, evidence=['x'])]
    assert statement_findings(model, 's', {'t': rows})


@pytest.mark.parametrize('self_paragraph', [False, True])
@pytest.mark.parametrize('suffix', [
    'finish(request) 함수를 호출하는 것은 아닙니다.',
    'finish(request) 함수를 호출해야 하는 것은 아닙니다.',
    'finish(request) 함수를 호출해서는 안 됩니다.',
    'finish(request) 함수를 호출합니다. 실제로 호출하지 않습니다.',
    'finish(request) 함수를 호출합니다 arbitraryEnglishWord.',
])
def test_negated_or_qualified_call_claims_do_not_waive_duplicates(suffix, self_paragraph):
    _assert_proof_cannot_waive(suffix, CALL_SOURCE, self_paragraph)


@pytest.mark.parametrize('self_paragraph', [False, True])
@pytest.mark.parametrize('source', [
    'struct Worker { void finish(Request *request); };',
    'void finish(Request *request);',
    'void Worker::finish(Request *request) {}',
    'struct Worker { void finish(Request *request) {} };',
    '// finish(request);\nreturn;',
    'const char *note = "finish(request)";',
    r'const char *note = "say \"finish(request)\"";',
    'const char *note = R"note(finish(request))note";',
    'const char *note = R"bad(finish(request);',
    'const char *note = "finish(request);',
])
def test_only_code_expression_calls_prove_novelty(source, self_paragraph):
    _assert_proof_cannot_waive('finish(request) 함수를 호출합니다.', source, self_paragraph)


@pytest.mark.parametrize('self_paragraph', [False, True])
@pytest.mark.parametrize('source', [
    '// dlHandle_ = nullptr;\nreturn;',
    '/* dlHandle_ = nullptr; */ return;',
    'const char *note = "dlHandle_ = nullptr";',
    r'const char *note = "say \"dlHandle_ = nullptr\"";',
    'const char *note = R"note(dlHandle_ = nullptr;)note";',
    'const char *note = R"bad(dlHandle_ = nullptr;',
])
def test_comments_and_literals_do_not_prove_member_writes(source, self_paragraph):
    _assert_proof_cannot_waive('dlHandle_를 초기화합니다.', source, self_paragraph)


@pytest.mark.parametrize('self_paragraph', [False, True])
@pytest.mark.parametrize('suffix', [
    'dlHandle_를 초기화하는 것은 아닙니다.',
    'dlHandle_를 초기화하지 않습니다.',
    'dlHandle_를 초기화합니다. 하지만 실제로 유지합니다.',
    'dlHandle_를 초기화합니다 arbitraryEnglishWord.',
])
def test_uncertain_member_write_claims_do_not_waive_duplicates(suffix, self_paragraph):
    _assert_proof_cannot_waive(suffix, 'dlHandle_ = nullptr; return;', self_paragraph)


def test_clear_call_and_member_write_evidence_still_preserves_new_information():
    assert _found_pair(BASE_CLAIM, BASE_CLAIM.removesuffix('.') + ', finish(request) 함수를 호출합니다.') == []
    detail = BASE_CLAIM.removesuffix('.') + ', dlHandle_를 초기화합니다.'
    assert _found_pair(BASE_CLAIM, detail, 'dlHandle_ = nullptr; return;') == []


def test_literal_return_text_is_not_code_return_guard_evidence():
    first = 'if (!module) { const char *note = "return nullptr;"; }'
    second = 'if (!proxy->isValid()) { return nullptr; }'
    before = 'Factory::create() 함수는 모듈이 없으면 nullptr를 반환하고, 서명이 유효하지 않으면 격리 방식을 선택합니다.'
    after = 'Factory::create() 함수는 서명이 유효하지 않으면 격리 방식을 선택하고, 프록시 생성이 실패하면 nullptr를 반환합니다.'
    assert _found_pair(before, after, first + '\n' + second, first, second)


def test_later_standalone_call_does_not_waive_earlier_internal_repetition():
    row = dict(text=BASE_CLAIM + ' ' + BASE_CLAIM + ' finish(request) 함수를 호출합니다.',
               quote=CALL_SOURCE, evidence=['x'])
    assert statement_findings(_sourced_model(CALL_SOURCE), 's', {'t': [row]})


CONTRACT_CLAIMS = [
    ('소유권은 호출자에게 전달됩니다.',
     '소유권은 호출자에게 전달되어야 하는 것은 아닙니다.', 'ownership is passed to the caller.'),
    ('이 함수는 스레드 안전합니다.',
     '스레드 안전해야 하는 것은 아닙니다.', r'\threadsafe'),
    ('참조를 저장합니다.',
     '참조를 저장하는 것은 아닙니다.', 'A reference is stored in the request.'),
    ('호출자는 동기화해야 합니다.',
     '호출자는 동기화해야 하는 것은 아닙니다.', 'This function shall be synchronized by the caller.'),
]


@pytest.mark.parametrize('self_paragraph', [False, True])
@pytest.mark.parametrize('positive,negative,source', CONTRACT_CLAIMS)
def test_negated_contract_obligation_is_not_a_novel_affirmative_contract(positive, negative, source, self_paragraph):
    _assert_proof_cannot_waive(negative, source, self_paragraph)
    _assert_proof_cannot_waive(positive + ' 하지만 실제로 그렇지 않습니다.', source, self_paragraph)
    _assert_proof_cannot_waive(positive.removesuffix('.') + ' arbitraryEnglishWord.', source, self_paragraph)


@pytest.mark.parametrize('positive,negative,source', CONTRACT_CLAIMS)
def test_clear_source_backed_affirmative_contracts_remain_novel(positive, negative, source):
    detail = BASE_CLAIM.removesuffix('.') + ', ' + positive
    assert _found_pair(BASE_CLAIM, detail, source) == []


@pytest.mark.parametrize('self_paragraph', [False, True])
@pytest.mark.parametrize('newline', ['\n', '\r\n'])
@pytest.mark.parametrize('hidden,suffix', [
    ('finish(request);', 'finish(request) 함수를 호출합니다.'),
    ('dlHandle_ = nullptr;', 'dlHandle_를 초기화합니다.'),
])
def test_cpp_spliced_line_comment_does_not_prove_execution(hidden, suffix, newline, self_paragraph):
    source = '// ignored code below ' + chr(92) + newline + hidden
    _assert_proof_cannot_waive(suffix, source, self_paragraph)
