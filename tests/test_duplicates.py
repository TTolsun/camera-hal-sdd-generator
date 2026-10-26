"""A1: 같은 근거로 같은 뜻을 되풀이한 문장을 결정적으로 반려한다.

문장 쌍은 공개 libcamera 문서(분석 커밋 2c4b67c0)에서 실제로 나온 것이다."""
from types import SimpleNamespace

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


def _ranged(**spans):
    """key -> (sha, file, line, end_line)"""
    return SimpleNamespace(evidence={f"s/{key}": dict(sha256=v[0], file=v[1], line=v[2], end_line=v[3]) for key, v in spans.items()})


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


def test_사실_서술과_실행_확인_항목은_같은_코드를_말해도_중복으로_보지_않는다():
    a, b = REPEATED[0]
    model = _model(**{"t/x": "h"})
    statements = {"t": [_statement(a, "x"), {**_statement(b, "x"), "kind": "limitation"}]}
    assert statement_findings(model, "s", statements) == []


def test_해시가_달라도_같은_파일의_줄_범위가_겹치는_발췌는_같은_근거로_본다():
    a, b = REPEATED[0]
    answers = {"tracking": [_statement(a, "completion")], "notification": [_statement(b, "contract")]}
    overlapping = _ranged(**{"tracking/completion": ("h1", "pipeline_handler.cpp", 458, 465),
                             "notification/contract": ("h2", "pipeline_handler.cpp", 463, 465)})
    assert len(statement_findings(overlapping, "s", answers)) == 1
    apart = _ranged(**{"tracking/completion": ("h1", "pipeline_handler.cpp", 458, 465),
                       "notification/contract": ("h2", "pipeline_handler.cpp", 600, 610)})
    assert statement_findings(apart, "s", answers) == []
    other_file = _ranged(**{"tracking/completion": ("h1", "pipeline_handler.cpp", 458, 465),
                            "notification/contract": ("h2", "camera.cpp", 460, 465)})
    assert statement_findings(other_file, "s", answers) == []
