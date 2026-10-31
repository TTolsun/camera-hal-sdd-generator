from sdd.manuscript import describe, lint, unwrap


def test_clean_manuscript_passes():
    body = ("`CameraDevice` 는 카메라마다 하나씩 만들어집니다 `device/CameraDevice.h:40`.\n\n"
            "1. `configureStreams()` 를 먼저 읽습니다.\n\n"
            "| 클래스 | 위치 |\n|---|---|\n| `CameraDevice` | `device/CameraDevice.h:40` |")
    assert lint(body) == []


def test_plain_sentence_endings_are_rejected():
    findings = lint("스트림 구성은 `configureStreams()` 가 담당한다 `device/CameraDevice.cpp:120`.")
    assert [f.rule for f in findings] == ["종결어미"]
    assert lint("버퍼 소유자는 확인이 필요함")[0].rule == "종결어미"
    # 인용이 문장 끝에 붙어도 "~합니다" 는 통과한다.
    assert lint("버퍼를 소유합니다 `device/CameraDevice.h:12`.") == []


def test_headings_and_tables_skip_sentence_rules():
    assert lint("## 스레드 모델 요약이다") == []
    assert lint("| 값 없음 | 확인 필요함 |") == []


def test_fenced_code_lines_are_skipped():
    assert lint("```cpp\nint run() { return 0; } // 실행한다\n```\n본문은 여기서 끝납니다.") == []


def test_unterminated_fence_is_itself_a_finding():
    findings = lint("```cpp\nint run();\n펜스가 닫히지 않은 채 본문이 이어진다")
    assert [f.rule for f in findings] == ["닫히지 않은 코드 펜스"]
    assert findings[0].line == 1


def test_dialogue_and_prompt_leak_are_rejected():
    assert [f.rule for f in lint("이 원고는 다음 절에서 검토를 요청합니다.")] == ["대화체·작업 보고"]
    assert [f.rule for f in lint("제공된 코드에서 콜백 등록을 확인했습니다.")] == ["원고·근거 언급"]


def test_paths_and_json_residue_are_rejected():
    assert [f.rule for f in lint("자세한 내용은 file://server/doc 에 있습니다.")] == ["절대 경로·줄 번호 링크"]
    assert [f.rule for f in lint("구현은 CameraDevice.cpp#L12 에 있습니다.")] == ["절대 경로·줄 번호 링크"]
    # Unix 절대 경로와 UNC 경로도 잡는다. 백틱 안이나 특수 문자로 시작하는 성분도 마찬가지다.
    assert [f.rule for f in lint("로그는 /var/log/camera 에 남습니다.")] == ["절대 경로·줄 번호 링크"]
    assert [f.rule for f in lint("원본은 `/tmp/CameraDevice.cpp:12` 에 있습니다.")] == ["절대 경로·줄 번호 링크"]
    assert [f.rule for f in lint("홈 로그는 /~user/log 에 남습니다.")] == ["절대 경로·줄 번호 링크"]
    assert [f.rule for f in lint("설정은 /구성파일/설정 아래에 있습니다.")] == ["절대 경로·줄 번호 링크"]
    assert [f.rule for f in lint("공유 폴더 \\\\build-server\\out 을 사용합니다.")] == ["절대 경로·줄 번호 링크"]
    assert [f.rule for f in lint("공유 폴더 \\\\-build\\out 을 사용합니다.")] == ["절대 경로·줄 번호 링크"]
    # 상대 경로 인용, 산술식의 빗금, C++ 주석 표기는 위반이 아니다.
    assert lint("비율은 3 / 4 입니다 `device/CameraDevice.h:12`.") == []
    assert lint("비율은 3 /4 로 계산합니다 `device/CameraDevice.h:12`.") == []
    assert lint("주석은 `//` 로 시작합니다 `device/CameraDevice.h:12`.") == []
    assert lint("인라인 주석은 // 기호로 시작합니다 `device/CameraDevice.h:12`.") == []
    assert [f.rule for f in lint('스레드 설명입니다."}')] == ["JSON 잔여물"]
    assert [f.rule for f in lint("첫 줄\\n둘째 줄입니다.")] == ["JSON 잔여물"]
    # 인라인 코드 안의 \n 과 상대 경로 인용은 위반이 아니다.
    assert lint("`a\\nb` 는 이스케이프 예시입니다 `device/CameraDevice.h:12`.") == []


def test_bold_line_heading_is_rejected():
    assert [f.rule for f in lint("**스레드 모델**")] == ["굵은 글씨 제목"]
    assert lint("**중요:** 이 함수는 잠금을 잡지 않습니다.") == []


def test_dma_device_interfaces_are_not_source_locations():
    for device in ('/dev/udmabuf', '/dev/dma_heap/system', '/dev/dma_heap/linux,cma'):
        assert lint(f"공급자는 `{device}` 장치입니다.") == []
    for source in ('/dev/udmabuf/source.cpp', '/dev/dma_heap/../source.cpp', '/dev/source.cpp',
                   '/tmp/source.cpp', '/dev/udmabuf#L12'):
        assert any(f.rule == '절대 경로·줄 번호 링크' for f in lint(f"위치는 `{source}` 에 있습니다."))
    assert any(f.rule == '절대 경로·줄 번호 링크' for f in lint("장치는 file:///dev/udmabuf 입니다."))


def test_unwrap_removes_outer_fence_only():
    inner = "본문입니다.\n\n```mermaid\ngraph TD\n```\n\n끝입니다."
    assert unwrap(f"```markdown\n{inner}\n```") == inner
    assert unwrap("포장 없는 본문입니다.") == "포장 없는 본문입니다."
    assert unwrap("```\n한 줄입니다.\n```") == "한 줄입니다."


def test_describe_makes_one_line_notes():
    notes = describe(lint("스트림 구성은 " + "아주 긴 설명 " * 20 + "함수가 담당한다"))
    assert len(notes) == 1
    assert notes[0].startswith("[종결어미] 1행 ")
    assert "…" in notes[0] and "\n" not in notes[0]


def test_코드_표기_없는_클래스_이름을_잡는다():
    from sdd.manuscript import lint
    names = {"libcamera::IPAManager", "IPAManager", "IPAProxy"}
    problems = lint("IPAManager 는 모듈을 만듭니다 `src/a.cpp:10`.", names)
    assert [p.rule for p in problems] == ["코드 표기 없는 클래스 이름"]
    assert "`IPAManager`" in problems[0].detail
    # 코드 표기 안에 있으면 잡지 않는다.
    assert lint("`IPAManager` 는 모듈을 만듭니다 `src/a.cpp:10`.", names) == []
    # 사실에 없는 이름은 이 규칙의 대상이 아니다.
    assert lint("SomeOtherThing 은 관계가 없습니다 `src/a.cpp:10`.", names) == []


def test_이름_목록이_없으면_코드_표기를_강제하지_않는다():
    from sdd.manuscript import lint
    assert lint("IPAManager 는 모듈을 만듭니다 `src/a.cpp:10`.") == []


def test_표와_제목에는_코드_표기_규칙을_적용하지_않는다():
    from sdd.manuscript import lint
    names = {"IPAManager"}
    assert lint("| IPAManager | src/a.cpp:10 |", names) == []
    assert lint("## IPAManager", names) == []


def test_A2_질문_문형이_답변에_섞이면_반려한다():
    leaked = ("공통 queueRequest 의 요청 추적이 stop() 시 완료와 어떤 관계가 있는지는, "
              "파이프라인 핸들러가 대기 중인 요청을 완료합니다 `src/p.cpp:10`.")
    assert [f.rule for f in lint(leaked)] == ["질문 문형 누출"]
    assert lint("대기 요청은 어디에서 기다립니까?")[0].rule == "질문 문형 누출"
    assert lint("완료되었는지를, 호출자가 확인합니다.")[0].rule == "질문 문형 누출"


def test_A2_평서문과_코드_표기_안의_물음표는_통과한다():
    assert lint("호출자는 반환값이 0인지 확인해야 합니다.") == []
    assert lint("`Adjusted ?` 표기는 원문 주석 그대로입니다.") == []
    assert lint("요청이 제출되었는지는 `requestCompleted` 신호로 확인합니다.") == []


def test_A1_같은_인용을_공유한_중복_문장은_린트에서_반려한다():
    first = ("파이프라인 핸들러는 stop()으로 파이프라인이 중지될 때 대기 중인 모든 요청의 완료를 보장하기 위해 "
             "completeRequest() 함수를 사용하여 완료 신호를 보내야 합니다. `src/p.cpp:10`")
    second = ("stop() 시 대기 중인 모든 요청이 자동으로 완료되도록 보장하며, 이때 completeRequest() 함수를 사용하여 "
              "요청 완료를 신호로 전달합니다. `src/p.cpp:10`")
    assert [f.rule for f in lint(first + "\n\n" + second)] == ["의미 중복 문장"]
    assert lint(first) == []


def test_한자_중국어_혼입은_본문에서_반려하고_코드_표기와_영문은_통과한다():
    assert [f.rule for f in lint("별도의闭上소로 배포할 수도 있습니다.")] == ["외국 문자 혼입"]
    assert [f.rule for f in lint("이를 우산術어라고 부릅니다.")] == ["외국 문자 혼입"]
    assert [f.rule for f in lint("かな도 섞이면 안 됩니다.")] == ["외국 문자 혼입"]
    assert lint("원문 `闭上` 표기는 코드이므로 통과합니다.") == []
    assert lint("libcamera adaptation은 다른 프레임워크와 연결하는 구성요소입니다.") == []


def test_키릴_글자가_한국어_문장에_섞이면_반려한다():
    assert [f.rule for f in lint("카메라 매니저가 카메라를 찾ывает")] == ["외국 문자 혼입"]
    assert [f.rule for f in lint("카메라를 찾ывает 기능을 제공합니다.")] == ["외국 문자 혼입"]
