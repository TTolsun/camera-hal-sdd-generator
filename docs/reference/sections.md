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
| `nav_section` | 독자 그룹 안의 작업별 소분류. 같은 이름의 문서를 모으며, 소분류와 그 안의 문서 순서는 설정에서 처음 나온 순서를 따릅니다. 생략하면 기존 메뉴를 유지합니다. 시나리오 하위 문서는 목록 문서의 소분류를 따릅니다. |
| `lead`, `reader` | 첫 줄에 굵게 보일 할 일, 이 문서의 독자. |
| `next` | `{title, link}`. 페이지 끝의 다음 단계. |
| `routes` | `[{q, to}]`. 페이지 첫 이동 표입니다. `q`는 독자가 할 일, `to`는 현재 페이지의 `#절-앵커` 또는 원고 기준 상대 Markdown 링크입니다. |
| `narration` | `facts`이면 모델 없이 facts로 씁니다. `per-scenario`는 `llm`도 받습니다. |
| `facts.classes` | 실을 클래스 glob. 전체 이름과 짧은 이름 모두 맞춥니다. 대소문자를 구분합니다. |
| `facts.functions` | 실을 자유 함수 glob. |
| `facts.packages` | 실을 패키지 glob(`src/*`). `per-package`는 이 패키지만 싣고, 범위 검사도 같은 기준을 씁니다. |
| `facts.impact_classes` | 다시 만들 계기로 볼 클래스. 생략하면 `facts.classes`. 인용용으로만 클래스를 넘기는 개요에서 `[]`로 둡니다. |
| `facts.impact_functions` | 다시 만들 계기로 볼 자유 함수. 생략하면 `facts.functions`. 선언이나 정의가 있는 파일이 바뀌면 절을 다시 만듭니다. |
| `facts.defines` | `table` 종류의 표시용 값. 현재 생성기는 compile DB의 `-D`를 모두 싣습니다. |
| `facts.reading_order` | 개요의 "코드를 처음 읽는 순서"에 쓸 시나리오 id. |
| `watch` | 추가로 감시할 경로입니다(소스 루트 상대 glob, `**` 지원). `design_topics.sources[].file`은 별도 watch 없이도 변경 시 해당 문서를 다시 만듭니다. |
| `diagram` | 이 섹션만의 그림 설정. 예: `{max_nodes: 24}`. 키는 [diagrams](config.md#diagrams)와 같습니다. |
| `answers` | 모델 설명이 답해야 할 질문 목록. |
| `semantic_review` | `true`이면 모델 설명의 구조 주장(상속·필드)을 facts와 대조합니다. |
| `show_evidence` | `true`이면 설명 아래에서 소스 발췌 원문을 펼쳐 볼 수 있습니다. |
| `design_generation` | `llm`이면 필수 설계 질문의 답변을 LLM이 작성합니다. 주제마다 `covers`로 질문을 연결하고 `statements`와 고정 `sha256`은 작성하지 않습니다. |
| `needs_human` | `true`이면 실행 확인이 필요하다는 안내를 붙입니다. |
| `prose_heading` | 설명 절의 제목. 기본은 "구조 설명". |
| `design_grounding` | 선택적 boolean. 이 LLM 섹션의 별도 모델 근거 대조 여부를 지정합니다. 생략하면 `review.design_grounding`을 따릅니다. 판정 통과는 사람 승인이 아닙니다. |

### 이동 안내 작성

`prose`의 이동 표를 직접 정하려면 다음처럼 씁니다. `q`에는 제목을 반복하지 말고 독자의 할 일을 적습니다. 링크 글자는 도착 문서·절 제목에서 가져옵니다.

```yaml
routes:
  - q: 콜백에서 다시 호출할 때의 제약을 확인합니다.
    to: '#콜백-재진입과-동기화'
  - q: 종료 후 자원을 회수하려고 합니다.
    to: overview.md#생성과-종료-순서
```

예시 앵커는 해당 제목이 있는 원고에서만 유효합니다. 생성 원고의 제목과 최종 HTML의 `id`를 확인하고 `verify-site`로 존재 여부를 검사합니다. 생략하면 본문 제목으로 이동 표를 자동 구성합니다. 종류별 생성기가 별도 이동 표를 만드는 색인·시나리오·패키지 문서는 그 표를 우선합니다.

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
| `sources[].start`, `end` | 발췌의 시작·끝 문자열. 시작 문자열은 파일 안에서 유일해야 합니다. `scope`를 지정하면 그 범위 안에서 유일해야 합니다. |
| `sources[].scope` | 선택할 문맥의 `start`, `end` 문자열. 범위 시작은 파일 안에서 유일해야 하며, 범위 끝을 넘어 발췌를 찾지 않습니다. 같은 문구가 여러 함수에 있을 때 담당 함수의 계약 안으로 검색을 한정합니다. |
| `sources[].sha256` | 사람이 본문을 대조한 발췌의 해시. 코드가 바뀌면 달라져서 다시 검토하게 합니다. 해시만 바꿔 통과시키지 않습니다. |
| `sources[].max_chars` | 발췌 길이 상한(기본 12000). |
| (파일 전체 발췌) | 발췌 앞뒤에 공백만 있으면 파일 전체를 고정한 근거입니다. 코드가 아닌 파일(튜닝 YAML, 설정 XML)이 바뀌어도 이 문서가 다시 만들어지고 해시가 맞으면 범위 검토에서 자동 분류합니다([범위 검사](../concepts/coverage.md#1단계-의미-없는-변경과-빌드-밖-파일의-자동-분류)). |
| `statements[].kind` | 생략하면 설명, `limitation`이면 실행 확인이 필요한 항목. limitation만으로는 질문의 답이 되지 않습니다. |

해시를 기록하는 절차는 [사람이 할 일](../inhouse/04-review.md#설계-설명을-쓰거나-다시-검토하기)에 있습니다.

반복되는 문구는 `scope: {start: '함수를 식별하는 유일한 문자열', end: '범위의 끝 문자열'}`로 문맥을 지정한 뒤 `start`와 `end`로 필요한 계약을 고릅니다. 두 단계 모두 시작 이후 처음 나타나는 끝 문자열까지 포함합니다. 이 기능은 괄호나 제어 흐름을 자동 분석하지 않으므로 중첩 분기에서 단순한 `}`를 함수 끝으로 가정하지 마세요. 조건·예외·호출 순서를 검토하고 전체 제어 흐름이 필요한 설명에는 함수 전체를 남깁니다. 잘못된 범위·중복 시작·범위 밖 끝은 검토 필요 상태로 남으며 다른 함수의 문구를 대신 사용하지 않습니다.

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

LLM은 `text`, `quote_id`(입력에 제공된 원문 구절 id), `covers`(질문 id), `kind`(`behavior` 또는 `limitation`)를 가진 설명 목록을 반환합니다. 생성기는 구절 id를 원문 `quote`와 출처 `evidence`로 변환하여 원고에 보존합니다. 기존의 원문 구절 직접 반환 형식도 같은 검사를 거칩니다. 원문 구절은 공백과 주석 줄 앞의 장식 문자 차이를 제외하고 연결된 발췌 안에 실제로 있어야 합니다. 질문별 답변 누락·원문 불일치·근거 불일치·문장 및 구조 검사 실패·입력 예산 초과가 있으면 선택한 기존 원고를 덮어쓰기 전에 실패합니다. 확인 필요 문장만으로 질문에 답했다고 처리하지 않습니다. 질문 id나 원문 구절의 연결 검사는 자연어 답변의 정확성·충분성을 증명하지 않습니다.

원고 frontmatter의 `generated_design`에는 답변과 입력·본문 지문이 함께 보존됩니다. 사이트 빌드와 증분 이월에서도 이 기록을 다시 검사하므로 원고를 전달할 때 frontmatter를 유지해야 합니다. 이 모드의 소스 선택 파일 변경은 `watch`가 없어도 영향 분석에 포함됩니다. 근거·질문이 바뀌면 재생성하고, 그대로이면 재검증 후 이월합니다. 상세 문서 본문은 개요의 근거로 사용하지 않으므로 두 문서는 관련 원본 소스 변경으로 함께 선택되도록 설정합니다.

Ollama 연결에서는 JSON 구조와 제공된 질문·구절 id를 제한하는 스키마를 전달합니다. 구절 id가 없거나 모델이 출처를 바꾸어 함께 보내면 거절합니다. 일반 `openai-compatible` 게이트웨이에는 스키마 API를 요구하지 않으며 같은 프롬프트·응답 파서·검사를 적용합니다. 모델 출력 형식이 올바르더라도 설명의 의미 검토는 여전히 필요합니다.

원문은 문단별 구절 id를 붙여 한 번만 제공합니다. 짧은 주변 코드도 입력에서 제거하지 않으므로 조건과 실행 문맥을 함께 읽을 수 있습니다. 모델이 원문을 다시 입력하면서 생기는 복사 오류를 줄이기 위한 방식이며, 설명 문단의 중복도 거절합니다. 내보내기에서는 id가 아닌 원고에 보존된 실제 구절·출처를 다시 검사합니다.

## 독자 프로필

`reader_profile: vendor-overview`, `reader_profile: vendor`, `reader_profile: vendor-assurance` 또는 `reader_profile: developer`를 `prose` 섹션에 지정하면 공통 필수 질문을 검사합니다. 생략하면 기존 설정 동작을 유지합니다.

| 프로필 | `design_requirements[].aspects`에 포함해야 하는 값 |
|---|---|
| `vendor-overview` | `capabilities`, `benefits` |
| `vendor-assurance` | `constraints`, `verification` |
| `vendor` (상세 구현 계약) | `inputs`, `ownership`, `completion`, `failure`, `verification` |
| `developer` | `entry`, `responsibility`, `boundaries`, `lifecycle`, `concurrency`, `verification` |
| `architecture` (기존 설정 호환) | `responsibility`, `boundaries`, `lifecycle`, `concurrency`, `verification` |

`vendor-overview`는 제품 개요, `vendor`는 연동 가이드, `vendor-assurance`는 지원 범위와 검증을 담당합니다. 한 페이지에 모든 질문을 넣지 않고 독자의 판단 단계별로 나눕니다. 기존 `vendor` 상세 계약도 유지합니다. 프로필을 바꾸면 질문·답변·근거를 검토하고 원고를 재생성하세요.

LLM 개요 생성에는 강점을 구체적 구현과 조건에 연결하고, 근거 없는 경쟁 우위·성능 수치·지원 기종·제품 완성도를 만들지 않도록 하는 공통 지침을 추가합니다. 자동 검사는 질문과 근거 연결을 확인하며 실제 강점이나 제품 성능을 인증하지 않습니다.

`developer`는 신입·타팀 개발자를 위한 프로필입니다. `entry`는 실제 첫 파일·진입점과 읽는 순서, `verification`은 증상별 확인 코드와 수정 후 검증 조건을 다룹니다. `architecture`는 이전 설정을 계속 읽기 위해 지원하며 Developer 문서의 기본값이 아닙니다. 기존 설정을 전환할 때는 이름만 바꾸지 말고 `entry`의 근거 있는 답변을 추가하고 읽기 과제를 다시 검증하세요.

각 질문에 `aspects: [ownership]`처럼 적용 항목을 적습니다. 한 질문이 여러 항목을 다룰 수 있습니다. 모든 항목이 선언되고, 모든 질문에 `covers`로 연결된 근거 있는 답변이 있어야 합니다. `limitation`만으로 답을 대신할 수 없습니다. 프로필 이름·항목 오류나 누락은 생성과 사이트 게시를 중단합니다.

프로필을 사용하는 설명은 한 산문 문단을 600자·4문장 이내로 나눕니다. 표·번호 단계·코드 원문은 이 분량 검사에서 제외합니다. 조건과 예외를 삭제해 분량을 맞추지 않습니다. 이 기준은 긴 문단을 막는 편집 검사이며 이해도 판정이 아닙니다.

[완성된 mini HAL 설정](../../examples/mini-hal/config/reader-sections.yaml)과 [사내 적용 절차·읽기 검증](../concepts/reader-quality.md)을 참고하세요. `show_evidence: true`이면 동일 페이지의 같은 발췌는 한 번만 싣고 주제별 설명에서 연결합니다.

## scenarios.yaml

질문별 그림은 `sdd.yaml`의 `visuals.file`에서 별도로 설정합니다. [사이트 구성의 질문별 그림](../concepts/site.md#질문별-그림)을 참고하세요.

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


## 작은 모델을 위한 질문 분할과 증분 재생성

서로 다른 근거 구절로 조건과 결과를 설명해야 할 때는 분할 질문에 `max_statements`를 지정할 수 있습니다. 범위는 1–8이며 기본값은 `answer_contract`가 있으면 1, 없으면 2입니다. 이 값은 목표 분량이 아니라 상한입니다. 늘려도 필수 용어, 근거 범위와 저장된 답변 검사는 유지됩니다.

`design_generation: llm` 주제에 `parts`를 지정하면 절 제목은 유지하면서 작은 질문별로 모델을 호출합니다. 각 항목에는 고유한 `id`, `question`, 해당 주제 안의 소스 ID 목록인 `sources`를 넣습니다. 선택적으로 아래의 `answer_contract`를 지정합니다. 답변이나 해시를 미리 넣을 수 없습니다. 전체 parts가 주제의 모든 소스 ID를 포함해야 하며, 한 항목이라도 검사를 통과하지 못하면 원고를 교체하지 않습니다. 분할 질문에는 그 질문과 지정한 발췌만 전달하고, 상위 질문 전체를 다시 답하도록 요구하지 않습니다.

한 항목이 여전히 복잡하면 `subquestions`에 중복 없는 세부 질문 2~4개를 지정할 수 있습니다. 각 질문은 800자 이내이며 같은 `sources`로 따로 작성합니다. 생성기는 `subpart_id`를 직접 부여하고 세부 질문마다 한 문단이 있는지 검사합니다. 원래 `question`과 `answer_contract`는 유지하며, 합친 답변에 원래 필수 용어·거부 패턴·근거 검사를 모두 적용합니다. [자동 보완 루프](../inhouse/reader-loop.md)도 이 설정을 제안할 수 있습니다.

```yaml
parts:
  - id: format
    question: 이 함수에서 입력 형식을 어떻게 선택합니까?
    sources: [import]
  - id: failure
    question: 이미지 생성 실패 시 반환값과 상태 변경은 무엇입니까?
    sources: [import]
```

`update`와 `generate --from-impact`에서는 기존 답변의 질문·소스 발췌·선택한 facts·생성 정책 지문을 비교합니다. 같은 주제는 근거를 다시 검사해 유지하고 변경된 주제만 LLM을 호출합니다. 원고에는 `topic_inputs`, `reused_topics`, `generated_topics`, `topic_agents`를 남겨 이전 작성자와 이번 모델을 구분합니다. 오래된 원고에 주제별 지문이 없으면 기존 주제 집합 전체의 지문이 일치할 때만 이월합니다. 본문 해시가 다르거나 지문을 검증할 수 없으면 재생성합니다. `generate`를 영향 옵션 없이 실행하면 선택한 주제를 모두 새로 생성합니다.

이 검사는 소스 일치와 생성 경로를 확인합니다. 문장 의미의 정확성이나 실제 하드웨어 동작을 승인하지 않습니다.

### 답변의 누락과 알려진 오류 검사

LLM 주제 또는 분할 질문의 `answer_contract`는 근거 유형과 최소 확인 항목을 선언합니다. 제품별 함수명·실패 패턴은 프로젝트 설정에 두고 공통 생성기에 넣지 않습니다.

```yaml
parts:
  - id: lifetime
    question: 완료 전 버퍼 유지에 관해 호출자가 지켜야 할 의무는 무엇입니까?
    sources: [buffer_contract]
    answer_contract:
      basis: contract
      required_terms: [[버퍼], [호출자], [완료]]
      reject_patterns:
        - pattern: '항상.{0,20}안전(?:합니다|하다)'
          message: 원문에 없는 무조건적인 안전 보장을 추가하지 마세요.
```

`basis`는 `contract`(호출자·구현자 의무), `implementation`(제시된 구현), `description`(문서상 기능), `measurement`(제시된 측정 근거), `investigation`(제시된 변수·반환값·분기에 근거한 조사 계획) 중 하나입니다. `contract`는 동작 문단에 한국어 의무 표현이 있는지 검사합니다. 나머지 유형은 프롬프트에서 해석 범위를 구분하며 측정이나 구현의 진실성을 자동 판정하지 않습니다. 조사 계획은 실제 실행 결과나 복구 보장이 아니며, 관찰하려고 상태 변경 함수를 다시 호출해서는 안 됩니다. 생성 요청에는 각 발췌의 실제 파일 경로도 전달합니다.

`required_terms`의 각 내부 목록은 대안입니다. `[[null, nullptr], [실패]]`이면 두 null 표기 중 하나와 `실패`가 필요합니다. ASCII 식별자 경계를 구분하므로 `Invalid`를 썼다고 `Valid`까지 설명한 것으로 세지 않습니다. 자연스러운 한국어 대안도 허용하되, 단어를 포함했다는 이유로 조건·인과·주체가 맞다고 판단하지 않습니다. `reject_patterns`는 알려진 오류의 정규식과 수정 안내이며, 긍정·부정 표현을 모두 시험하여 과잉 차단을 피해야 합니다.

계약을 지정한 분할 질문은 한 문단으로 답하므로 결과와 필수 조건을 분리하지 않습니다. 계약 없는 기존 분할 질문은 두 문단까지 허용합니다. 긴 질문은 조건을 삭제하지 말고 나누세요. 구조화된 답변에는 일반 산문의 80자 하한을 적용하지 않습니다. 짧고 완전한 답을 늘리도록 강요하는 대신 빈 답변·근거·질문 연결과 계약을 검사합니다.

생성기가 기록한 `part_id`로 각 분할 질문의 누락과 다른 질문의 근거 사용을 저장 원고에서도 다시 검사합니다. 재시도에는 원래 근거와 검사 오류를 전달합니다. `standard` 모드는 마지막 실패 답변도 함께 전달하며, `focused` 모드는 같은 오류 문장을 반복하지 않도록 실패 답변을 제외합니다. 실패가 계속되면 기존 원고를 보존합니다. 원문 `caller shall check`에 대응하는 호출자의 확인 의무는 근거 부족 문장으로 거절하지 않습니다. 이 예외도 인용 원문 검사를 생략하지 않습니다. 이러한 문자 기반 검사는 의미 검토를 대체하지 않습니다.

설명 문서별 `design_prompt: standard|focused`는 `review.design_prompt`를 해당 문서에서만 재정의합니다. 작은 모델의 실제 비교 결과에 따라 선택할 수 있으며, 근거·인용·계약 검사는 어느 모드에서도 유지됩니다.

`design_topics` 항목에도 `design_prompt`를 지정할 수 있습니다. 주제 설정이 문서 설정보다 우선하며, 해당 주제의 작성 지침이 바뀌면 그 주제를 다시 생성합니다. 계산식과 복합 제어 흐름의 실제 모델 평가 결과가 다를 때 사용합니다.
