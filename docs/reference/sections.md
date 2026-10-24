# sections.yaml과 scenarios.yaml 참조

**문서 한 편은 `sections.yaml`의 항목 하나입니다.** 어떤 클래스를 싣고, 어떻게 쓰고, 어떤 변경에 다시 만들지를 이 항목이 정합니다. 키의 뜻은 이 문서 한 곳에만 적습니다.

| 지금 확인할 내용 | 이동할 절 |
|---|---|
| 문서 종류(kind)를 고릅니다. | [문서 종류](#문서-종류) |
| 섹션 항목에 쓸 키를 찾습니다. | [섹션 키](#섹션-키) |
| 설계 설명을 소스에 연결합니다. | [설계 질문과 근거](#설계-질문과-근거) |
| 호출 흐름의 진입점을 적습니다. | [scenarios.yaml](#scenariosyaml) |
| HAL3 진입점을 적는 규칙을 봅니다. | [HAL3 진입점 작성 규칙](#hal3-진입점-작성-규칙) |

## 문서 종류

| `kind` | 만드는 것 | 모델 호출 |
|---|---|---|
| `prose` (기본) | 클래스·함수 근거로 쓴 설명 한 편. `design_topics`가 있으면 소스에 연결한 설명을 그대로 씁니다. | `narration: facts`이거나 모든 주제에 `statements`가 있으면 없음 |
| `per-package` | 패키지마다 한 절. | `narration: facts`이면 없음(클래스·함수 표만) |
| `per-scenario` | `scenarios.yaml`의 진입점마다 한 페이지와 목록. | `narration: facts`(기본)이면 없음 |
| `table` | `-D` 플래그와 `#if` 분기 위치 표. | 없음 |
| `index` | 문서 목록. | 없음 |
| `manual` | 사람이 쓰는 문서. 생성기는 빈 자리만 만들고 덮어쓰지 않습니다. | 없음 |

모든 클래스를 한 문서가 다루게 하려면 `per-package` + `narration: facts` + `facts.classes: ['*']` + `facts.functions: ['*']`로 색인을 둡니다. 그러면 새 코드가 범위 검사 관문에 걸리지 않고 색인에 실립니다. 예시는 [libcamera 설정](../../examples/libcamera/config/sections.yaml)의 `component-index`입니다.

## 섹션 키

| 키 | 뜻 |
|---|---|
| `id`, `title`, `output` | 식별자, 제목, 원고 파일(`sdd_dir` 기준). |
| `group` | 사이트 왼쪽 메뉴 그룹. 순서는 `site.nav_groups`. |
| `lead`, `reader` | 첫 줄에 굵게 보일 할 일, 이 문서의 독자. |
| `next` | `{title, link}`. 페이지 끝의 다음 단계. |
| `narration` | `facts`이면 모델 없이 facts로 씁니다. `per-scenario`는 `llm`도 받습니다. |
| `facts.classes` | 실을 클래스 glob. 전체 이름과 짧은 이름 모두 맞춥니다. 대소문자를 구분합니다. |
| `facts.functions` | 실을 자유 함수 glob. |
| `facts.packages` | 실을 패키지 glob(`src/*`). `per-package`는 이 패키지만 싣고, 범위 검사도 같은 기준을 씁니다. |
| `facts.impact_classes` | 다시 만들 계기로 볼 클래스. 생략하면 `facts.classes`. 인용용으로만 클래스를 넘기는 개요에서 `[]`로 둡니다. |
| `facts.impact_functions` | 다시 만들 계기로 볼 자유 함수. 생략하면 `facts.functions`. 선언이나 정의가 있는 파일이 바뀌면 절을 다시 만듭니다. |
| `facts.defines` | `table` 종류의 표시용 값. 현재 생성기는 compile DB의 `-D`를 모두 싣습니다. |
| `facts.reading_order` | 개요의 "코드를 처음 읽는 순서"에 쓸 시나리오 id. |
| `watch` | 이 경로가 바뀌면 다시 만듭니다(소스 루트 상대 glob, `**` 지원). |
| `diagram` | 이 섹션만의 그림 설정. 예: `{max_nodes: 24}`. 키는 [diagrams](config.md#diagrams)와 같습니다. |
| `answers` | 모델 설명이 답해야 할 질문 목록. |
| `semantic_review` | `true`이면 모델 설명의 구조 주장(상속·필드)을 facts와 대조합니다. |
| `show_evidence` | `true`이면 설명 아래에서 소스 발췌 원문을 펼쳐 볼 수 있습니다. |
| `design_generation` | `llm`이면 필수 설계 질문의 답변을 LLM이 작성합니다. 주제마다 `covers`로 질문을 연결하고 `statements`와 고정 `sha256`은 작성하지 않습니다. |
| `needs_human` | `true`이면 실행 확인이 필요하다는 안내를 붙입니다. |
| `prose_heading` | 설명 절의 제목. 기본은 "구조 설명". |

## 설계 질문과 근거

책임·상태·소유권·종료·스레드 같은 계약은 클래스 표만으로 설명되지 않습니다. 사람(또는 에이전트)이 소스와 대조해 쓴 설명을 소스 발췌에 묶어 둡니다. 동작 원리와 한계는 [설계 근거](../concepts/design-evidence.md)에 있습니다.

```yaml
design_requirements:          # 이 문서가 반드시 답할 질문
  - id: shutdown
    question: 정지할 때 대기 요청은 어떻게 반환됩니까?
design_topics:
  - id: stop
    title: 종료 계약
    question: 대기 요청의 취소와 완료 순서는 무엇입니까?
    sources:                  # 소스 발췌: 파일 안에서 한 번만 나오는 시작·끝 문자열
      - id: stop
        file: device/CameraDevice.cpp
        start: "int CameraDevice::flush()"
        end: "return 0;\n}"
        sha256: "<extract 뒤 facts.json evidence 에 나오는 값>"
    statements:
      - text: "소스와 대조한 설명."
        evidence: [stop]      # 근거 발췌 id
        covers: [shutdown]    # 답하는 질문 id
      - text: "실기기에서만 확인할 수 있는 점."
        kind: limitation
        evidence: [stop]
        covers: [shutdown]
```

| 키 | 뜻 |
|---|---|
| `sources[].start`, `end` | 발췌의 시작·끝 문자열. 시작 문자열은 파일 안에서 유일해야 합니다. |
| `sources[].sha256` | 사람이 본문을 대조한 발췌의 해시. 코드가 바뀌면 달라져서 다시 검토하게 합니다. 해시만 바꿔 통과시키지 않습니다. |
| `sources[].max_chars` | 발췌 길이 상한(기본 12000). |
| (파일 전체 발췌) | 발췌 앞뒤에 공백만 있으면 파일 전체를 고정한 근거입니다. 코드가 아닌 파일(튜닝 YAML, 설정 XML)이 바뀌어도 이 문서가 다시 만들어지고 해시가 맞으면 범위 검토에서 자동 분류합니다([범위 검사](../concepts/coverage.md#1단계-의미-없는-변경과-빌드-밖-파일의-자동-분류)). |
| `statements[].kind` | 생략하면 설명, `limitation`이면 실행 확인이 필요한 항목. limitation만으로는 질문의 답이 되지 않습니다. |

해시를 기록하는 절차는 [사람이 할 일](../inhouse/04-review.md#설계-설명을-쓰거나-다시-검토하기)에 있습니다.

### 필수 질문의 LLM 자동 생성

독자와 질문, 소스 선택 범위를 설정하면 생성기가 현재 커밋의 발췌를 수집하여 답변을 만듭니다. 다음 예제에는 미리 작성한 본문이 없습니다.

```yaml
design_generation: llm
design_requirements:
  - id: shutdown
    question: 종료할 때 하드웨어 구현자가 지킬 계약은 무엇입니까?
design_topics:
  - id: stop
    title: 종료 책임
    question: 공통 종료 처리와 하드웨어 구현의 책임을 구분하세요.
    covers: [shutdown]
    sources:
      - id: stop
        file: device/CameraDevice.cpp
        start: "int CameraDevice::flush()"
        end: "return 0;\n}"
show_evidence: true
```

각 필수 질문은 정확히 한 주제에 연결합니다. 소스 해시는 생성기가 수집하므로 설정에 고정하지 않습니다. `agent.kind`에는 실제 모델 연결(`ollama` 또는 `openai-compatible`)이 필요하며 `dry-run`으로 필수 답변을 대신할 수 없습니다. 모델 주소와 이름은 프로젝트 실행 환경에서 설정합니다.

LLM은 `text`, `evidence`(소스 id), `covers`(질문 id), `kind`(`behavior` 또는 `limitation`)를 가진 설명 목록을 반환합니다. 질문별 답변 누락·근거 불일치·문장 및 구조 검사 실패·입력 예산 초과가 있으면 선택한 기존 원고를 덮어쓰기 전에 실패합니다. 확인 필요 문장만으로 질문에 답했다고 처리하지 않습니다. 질문 id의 연결 검사는 자연어 답변의 정확성·충분성을 증명하지 않습니다.

원고 frontmatter의 `generated_design`에는 답변과 입력·본문 지문이 함께 보존됩니다. 사이트 빌드와 증분 이월에서도 이 기록을 다시 검사하므로 원고를 전달할 때 frontmatter를 유지해야 합니다. 이 모드의 소스 선택 파일 변경은 `watch`가 없어도 영향 분석에 포함됩니다. 근거·질문이 바뀌면 재생성하고, 그대로이면 재검증 후 이월합니다. 상세 문서 본문은 개요의 근거로 사용하지 않으므로 두 문서는 관련 원본 소스 변경으로 함께 선택되도록 설정합니다.

Ollama 연결에서는 제공된 질문·소스 id만 반환하도록 JSON 스키마도 전달합니다. 일반 `openai-compatible` 게이트웨이에는 스키마 API를 요구하지 않으며 같은 프롬프트·응답 파서·검사를 적용합니다. 모델 출력 형식이 올바르더라도 설명의 의미 검토는 여전히 필요합니다.

## scenarios.yaml

```yaml
defaults:
  glob: ["**/*.cpp"]
  depth: 5
  hide:
    names: ["ALOG*", "ATRACE*"]      # 흐름을 덮는 로그·트레이스 호출을 숨깁니다
scenarios:
  - id: process_capture_request
    title: 캡처 요청 처리
    from: "vendor::camera::CameraDevice::processCaptureRequest(camera3_capture_request_t *)"
    # 정의: device/CameraDevice.cpp:120
    depth: 6
```

| 키 | 뜻 |
|---|---|
| `id`, `title` | 페이지 이름과 제목. |
| `from` | 진입 함수의 시그니처. 규칙은 아래 절에 있습니다. |
| `depth` | 따라갈 호출 깊이. |
| `glob` | 정의를 찾을 파일. |
| `hide.owners`, `hide.names` | 그림·요약에서 숨길 호출의 소유 클래스와 이름 glob. 전체 기록에는 남습니다. |
| `focus` | `[{title, names, src, dst}]`. 요약에 올릴 호출을 직접 고릅니다. 근거가 없으면 실패합니다. |

`defaults`의 값은 각 시나리오에 합쳐지고, 시나리오에 적은 값이 우선합니다.

## HAL3 진입점 작성 규칙

1. **클래스와 네임스페이스까지 적습니다.** 완전한 이름은 접미사만 같은 다른 정의보다 우선합니다.
2. **인자 타입을 소스와 같게 적습니다.** 인자 이름은 빼고, 공백 차이는 무시합니다. `struct` 키워드는 있어도 없어도 됩니다.
3. **모호하면 추출이 멈춥니다.** 같은 이름의 정의가 여럿이고 시그니처로 하나를 고를 수 없으면 후보 목록을 보여 주고 중단합니다. 엉뚱한 함수에서 시작한 흐름이 문서에 실리지 않게 하기 위해서입니다.
4. **ops 표의 trampoline에서 시작할 수 있습니다.** `camera3_device_ops`의 정적 함수가 `dev->priv`를 캐스트해 멤버 함수를 부르면, 그 호출을 따라갑니다.
5. **framework 콜백은 경계입니다.** `process_capture_result`, `notify` 같은 `camera3_callback_ops` 호출은 "함수 포인터, 정적 추적 불가"로 표시됩니다. 큐를 건너 다른 스레드가 처리하는 흐름은 그 처리 함수를 별도 시나리오로 등록합니다.

다음 단계: 명령과 종료 코드는 [명령 참조](cli.md)를 읽습니다.
