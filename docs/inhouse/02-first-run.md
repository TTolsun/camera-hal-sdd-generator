# 2단계: 질문 하나로 첫 실행 확인하기

사내 템플릿을 복사한 뒤 개발자가 실제로 답해야 할 질문 하나를 고르세요. 예를 들어 “요청 제출이 성공한 뒤 언제 완료됐다고 판단하고, 언제 버퍼를 재사용할 수 있나요?”처럼 소스 범위를 한정할 수 있는 질문부터 시작합니다. 아래 절차의 공통 기능은 공개 입력에서 확인할 수 있습니다. 사내 제품의 빌드, 모델 인증, 코드 열람, 게시 권한은 해당 환경에서 확인해야 합니다.

```
설정·빌드 확인 → 근거 추출 → 호출 없는 계획 → 초안과 독립 검토 → 로컬 확인
                                               실패·중단 → 같은 입력에서 재개 ↗
```

## 1. 설정 디렉터리 만들기

생성기 저장소의 [사내 설정 템플릿](../../examples/inhouse-template/)을 생성기 저장소 옆으로 복사합니다. 사내 클래스명과 설명이 들어가므로 이 디렉터리는 사내 저장소에서 관리합니다.

```text
workspace/
  camera-hal-sdd-generator/   # 생성기 (이 저장소)
  hal-camera-analysis/        # 분석 전용 HAL 체크아웃
  hal-sdd-project/            # examples/inhouse-template 을 복사한 곳
```

## 2. sdd.yaml 채우기

복사한 `sdd.yaml`에서 `<...>`로 표시한 칸을 채웁니다.

1. `site.source_url`: 인용을 연결할 사내 코드 열람 주소. Gitiles가 아니면 `source_link`도 바꿉니다.
2. `source.ndk_build.args`: 제품 빌드와 같은 ndk-build 인자.
3. 경로가 위 배치와 다르면 `source.root`, `ndk_build.project_dir`, `paths.*`를 고칩니다.

템플릿의 생성 예시는 Codex CLI, `gpt-6.1-terra`, 추론 강도 `high`입니다. 사내에서 승인한 생성 CLI가 다르면 `sdd.local.yaml`에서 `runner`, `command`, `model`, `args`를 함께 지정하세요. 검토용 CLI는 `sdd.review.example.yaml`을 복사한 `sdd.review.yaml`에서 별도로 지정합니다. CLI 인증에는 조직에서 승인한 방식을 사용하고 설정 인자에 인증 토큰을 넣지 않습니다. [실행기 설정](cli-agents.md)

템플릿은 Mermaid 동봉과 승인 전 로컬 미리보기를 사용합니다. 코드 열람 호스트, `site.source_link_template`, 정적 자산 위치, 게시 위치와 승인 정책은 사내 환경에 맞게 정하세요. 로컬 시험 후 실제로 게시할 때는 `site.require_approval`을 운영 정책에 맞게 설정합니다. [설정 참조](../reference/config.md)

## 3. 무엇을 문서화할지 정하기

실제 제품에서 빌드한 범위와 문서가 답할 질문을 정합니다.

1. `config/scenarios.yaml`의 `<namespace>`와 시그니처를 실제 정의로 바꿉니다. 규칙은 [HAL3 진입점 작성 규칙](../reference/sections.md#hal3-진입점-작성-규칙)에 있습니다.
2. `config/sections.yaml`의 클래스 패턴을 사내 이름에 맞추고, `vendor-contract`·`overview`의 필수 질문에 소스 근거와 답변을 작성합니다. 빈 계약으로는 생성할 수 없습니다. [계약 작성 절차](contract-authoring.md)를 따릅니다. 사내 에이전트가 이 작업을 직접 수행할 수 있습니다.
3. `config/glossary.yaml`에 사내 약어의 뜻을 적습니다. `export-site`는 뜻이 없는 약어를 알려 주고 게시를 멈춥니다. 형식은 [glossary.yaml 참조](../reference/glossary.md)에 있습니다.
4. `components` 섹션은 **구성 요소 색인**으로 켜 두었습니다(`narration: facts`, 클래스·함수 `'*'`). 빌드한 모든 코드가 한 문서에 실리므로, 문서가 다루지 않는 코드가 바뀔 때마다 갱신이 멈추는 일이 크게 줄어듭니다. 끄지 않습니다.

## 4. 환경을 점검하고 근거 추출하기

`extract` 후에는 발췌 원문을 확인하고 해시와 답변을 채운 뒤 `generate`를 실행합니다. 첫 설정만으로 계약의 의미를 자동 완성하지 않습니다. 이 문서는 NDK-build 사례이며 다른 빌드는 [환경별 선택](agent.md#1-환경과-데이터-경계)을 따릅니다.

생성기 저장소 루트에서 `doctor`를 실행하세요. DB가 없으면 NDK 템플릿에서는 `compdb`를 실행합니다. Soong, CMake 등 다른 빌드에서는 제품 빌드에서 만든 DB와 생성 헤더를 준비하고 `source.compile_commands`를 지정하세요. 필요하면 `compdb --normalize`로 분석용 사본을 준비합니다.

```bash
uv run sdd --config ../hal-sdd-project/sdd.yaml doctor
# DB가 없는 NDK 템플릿에서 실행합니다.
uv run sdd --config ../hal-sdd-project/sdd.yaml compdb
uv run sdd --config ../hal-sdd-project/sdd.yaml doctor
uv run sdd --config ../hal-sdd-project/sdd.yaml extract
```

`doctor --header <경로>`를 반복 지정하면 필요한 생성 헤더의 존재를 확인할 수 있습니다. `extract`에서는 파싱 오류와 미해결 진입점이 모두 0개여야 합니다. DB와 헤더가 다른 제품 구성이나 커밋에서 왔다면 해당 구성에서 다시 빌드하세요. `doctor`의 로컬 점검과 `extract`에는 문서 생성 호출이 없습니다. CLI의 인증·네트워크·모델 접근은 해당 CLI에서 확인하세요. 실행 파일 확인만으로 인증 성공을 판정할 수 없습니다.

## 5. 호출 없이 계획을 확인한 뒤 질문 하나를 실행하기

첫 실행에는 질문과 필요한 그림 하나를 담은 작은 섹션을 준비합니다. 아래 명령의 `first-question`은 그 섹션의 ID로 바꿉니다. 작은 설정에 `overview.md`가 없다면 섹션의 `next`를 실제로 열 수 있는 관련 자료로 지정하세요. 기본 다음 링크가 가리키는 페이지가 없으면 독립 검토와 로컬 링크 검사에서 멈춥니다. 템플릿의 전체 문서 범위는 운영에 사용할 수 있습니다. [질문·발췌 작성](contract-authoring.md) · [질문별 시각화 기준](../concepts/reader-quality.md#항목별-시각화-검토)

```bash
uv run sdd --config ../hal-sdd-project/sdd.yaml generate --sections first-question --plan-only
```

출력된 계획 파일을 로컬에서 여세요. `facts`와 `documents`에서 추출·문서 범위를, `units`에서 질문, 근거 ID, 입력 문자 수, 새 생성과 재사용 후보를 확인합니다. 앞선 답변에 의존하는 후보는 실제 실행에서 결정됩니다. 그림은 `visuals`에서 확인합니다. 설정한 독립 검토의 실제 요청은 생성한 원고가 나온 뒤에 구성됩니다. 비교 가능한 시간·토큰 표본이 없으면 계획에 추정 불가로 표시합니다. 이 단계는 모델 호출 0회이며 초안, 검토 결과나 승인 상태를 만들지 않습니다.

계획의 `execution`과 `independent_review.profile`에서 실행 파일, 래퍼 인자, 모델, 추가 인자와 timeout을 확인하세요. 검토할 질문은 `paths.consistency_file`에, 검토 실행기는 `paths.consistency_profile`에 지정합니다. 아래 예에서 `match`는 근거 대조에 포함할 원고 문장을 선택하는 정규식입니다. 핵심 답변이 빠지지 않는지 검토 보고서의 `claims`에서 확인하세요.

```yaml
contracts:
  - id: first-question
    question: 요청이 완료된 뒤 버퍼를 언제 재사용할 수 있나요?
    primary: first-question.md
    documents: [first-question.md]
    match: '완료|재사용'
```

실행하기 전에 첫 실행의 한도를 로컬 설정에 적습니다. 예를 들어 `review.max_calls: 4`, `review.max_seconds: 900`, `review.max_retries: 1`을 지정할 수 있습니다. 호출·시간 상한을 생략하거나 0으로 두면 해당 상한이 없습니다. 실패한 호출과 재시도도 호출 시도에 포함됩니다. `max_retries`의 0은 최초 시도만 허용합니다. 이 값은 응답 검증에서 재시도를 지원하는 경로에 적용되며 인증 실패나 독립 계약 대조를 자동으로 반복하지 않습니다.

`review.max_calls`와 `review.max_seconds`는 생성과 계약 대조의 각 호출 명령에 따로 적용됩니다. `review.document_max_*`는 장부의 문서 범위에서 실행되는 설계 답변·계약 대조에 적용됩니다. 준비 명령이나 그 범위 밖의 렌더링까지 제한하려면 별도 시간 측정이 필요합니다. 진행 중인 CLI에는 `agent.timeout_sec`와 남은 실행·문서·작업 시간 중 가장 짧은 값이 적용됩니다. 여러 명령과 재개에 걸친 누적 상한이 필요하면 `publication.operation_id`와 `publication.budget`을 사용합니다. [발행 입력과 작업 기록](../concepts/publication-inputs.md)

```bash
uv run sdd --config ../hal-sdd-project/sdd.yaml generate --sections first-question
uv run sdd --config ../hal-sdd-project/sdd.yaml audit-consistency
```

## 6. 결과를 확인하고 중단 지점에서 재개하기

각 명령이 출력한 `build/generation-runs/<실행 ID>.json`을 여세요. 생성 장부의 `publication_plan`은 해당 실행의 계획을 가리킵니다. `documents`와 `counts`는 완료·재사용·실패·미시작 설계 답변과 계약 대조 단위를 보여 줍니다. `calls`의 `section`과 `tag`로 단위 비용을 찾고, `section`이 비어 있는 공통 호출과 실행 전체 시간을 따로 봅니다. 실패·중단 시도도 시간과 호출 합계에 들어갑니다.

`calls`에서 원본 stdout·stderr와 완료 응답의 영수증을, `review_attempt`에서 이번 검토 결과를 찾을 수 있습니다. Codex의 단일 완료 이벤트에 입력·출력 토큰이 있으면 각 합계를 한 번만 기록합니다. 캐시 입력과 추론 출력은 별도로 더하지 않습니다. 이벤트가 없는 호출이나 장부에서 해석하지 않는 CLI의 토큰은 미계측입니다. 토큰을 구독 요금이나 실제 청구액으로 환산하지 않으며 실행 단위의 강제 토큰 상한은 제공하지 않습니다.

| 확인 결과 | 다음 행동 |
| --- | --- |
| CLI 미설치·인증·네트워크 실패 | 장부의 원인과 로컬 stderr를 확인합니다. 선택한 CLI의 설치·인증·연결을 복구한 뒤 같은 명령을 실행합니다. |
| 근거 부족 또는 컨텍스트 한도 초과 | 표시된 질문의 근거, 범위와 입력 한도를 확인합니다. 입력을 바꿨다면 `extract`와 계획을 다시 확인합니다. |
| 호출 또는 시간 한도 소진 | 장부의 완료 항목과 제한을 확인합니다. 실행별 한도라면 같은 명령으로 체크포인트를 확인할 수 있습니다. 누적 상한을 소진했다면 승인된 범위에서 남은 일을 결정합니다. |
| 초안 또는 자동 검토 완료 | 원고, `design-review.json`과 `consistency-review.json`을 엽니다. 미해결 판정과 사람 승인 대기 상태를 확인합니다. |

재개할 때는 실패한 장부의 `resume_argv`에 기록된 명령과 같은 설정·소스 커밋·섹션을 사용하세요. `build`의 facts, 원본 영수증과 체크포인트, 기존 원고를 보존합니다. 명시한 CLI 모델과 입력이 맞는 완료 설계 답변은 `review.cli_checkpoint: true`일 때 재검증한 뒤 재사용합니다. 완성되지 않은 호출, 모델을 CLI 기본값에 맡긴 경우, 입력이 바뀐 단위는 다시 호출될 수 있습니다. 근거 검토에는 해당 검토의 체크포인트를 사용합니다. 재개 전후의 새 호출과 재사용을 장부에서 확인하세요.

### 로컬 사이트 확인

Mermaid 사본을 준비하고 로컬 사이트를 확인합니다. 사내 미러가 있으면 `--registry`를 지정하고, 외부 네트워크 없이 반입한 파일을 사용할 때는 `--tarball`을 지정하세요. 전체 설정에 아직 생성하지 않은 페이지가 있다면 작은 시험 설정으로 사이트를 내보내거나 원고와 Mermaid 파일을 먼저 확인합니다.

```bash
uv run sdd --config ../hal-sdd-project/sdd.yaml fetch-mermaid
```

```bash
uv run sdd --config ../hal-sdd-project/sdd.yaml export-site
```

```bash
uv run sdd --config ../hal-sdd-project/sdd.yaml verify-site
```

| 명령 | 확인할 값 | 어긋나면 |
|---|---|---|
| `compdb` | `compile DB: ... (TU N 개, ...)` 출력 | [문제 해결](troubleshooting.md) |
| `doctor` | 로컬 필수 항목에 `[!!]` 표시가 없음 | [문제 해결](troubleshooting.md) |
| `extract` | `파싱 오류 0 개`, `진입점 못 찾음 0 개`, 클래스 수가 HAL 규모와 비슷함 | [문제 해결](troubleshooting.md) |
| `generate` | 원고마다 `status: ok` 또는 `needs-review` | `needs-review`는 [4단계](04-review.md)에서 처리합니다. |
| `verify-site` | `broken_links: 0` | 링크가 깨진 채 게시하지 않습니다. |

결과는 `hal-sdd-project/build/site/index.html`에서 엽니다. 이 미리보기와 자동 검토 결과는 사람 승인이나 게시 결과를 기록하지 않습니다. 실제 게시 전에는 코드 링크를 열어 볼 수 있는지, Mermaid가 표시되는지, 해당 버전의 사람이 승인했는지 확인하세요.

## compile DB가 어떻게 바뀌는가

ndk-build가 만든 원본 DB는 libclang이 그대로 읽지 못합니다. 생성기가 자동으로 고쳐 씁니다. 따로 할 일은 없습니다.

```
ndk-build compile_commands.json        (원본: 상대 경로, ccache, 내장 헤더 없음)
        │  원본은 고치지 않음
        ├─ ccache 같은 wrapper 제거
        ├─ -I·file·--sysroot 를 절대 경로로, -working-directory 추가
        └─ DB 의 NDK clang -print-resource-dir → -resource-dir 추가
        ▼
build/compdb/compile_commands.json     (source.compile_commands 가 원본을 가리킬 때)
```

- DB의 컴파일러 이름이 `clang`·`clang++`·`clang-18` 같은 형태가 아니면 실행하지 않고 멈춥니다. 이때 `source.ndk_build.clang`에 신뢰하는 NDK clang 경로를 적습니다.
- 원본을 고치지 않는 이유: 원본이 HAL 저장소 안에 있으면 작업 트리가 바뀌어 `sdd update`가 멈추기 때문입니다.

다음 단계: 문서를 커밋마다 자동으로 갱신하려면 [3단계: 문서 갱신 시스템](03-update-system.md)을 엽니다.
