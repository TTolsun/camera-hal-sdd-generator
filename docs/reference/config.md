# sdd.yaml 설정 참조

**설정 키의 뜻과 기본값은 이 문서 한 곳에만 적습니다.** 다른 문서는 키 이름만 쓰고 이 문서로 연결합니다.

- 상대 경로는 설정 파일이 있는 디렉터리 기준입니다.
- 같은 이름의 `*.local.yaml`(예: `sdd.local.yaml`)이 있으면 그 값으로 덮어씁니다. 로컬 파일은 Git에서 제외합니다.
- 명령은 셸 문자열이 아니라 인자 목록(`["ndk-build", "compile_commands.json"]`)으로 적습니다.

| 지금 확인할 내용 | 이동할 절 |
|---|---|
| 소스와 compile DB를 지정합니다. | [source](#source) |
| 출력 위치와 공용 자산 위치를 바꿉니다. | [output과 paths](#output과-paths) |
| 추출 방식을 정합니다. | [facts와 tools](#facts와-tools) |
| 설명 모델과 검사 정책을 정합니다. | [agent](#agent), [review](#review) |
| 문서 분량·그림·사이트를 정합니다. | [documentation](#documentation), [diagrams](#diagrams), [site](#site) |
| 커밋마다 갱신하고 게시합니다. | [update](#update), [automation](#automation) |

## source

| 키 | 기본값 | 뜻 |
|---|---|---|
| `root` | `../hal-camera` | 분석할 소스 저장소. `sdd update`가 커밋마다 체크아웃하므로 분석 전용 체크아웃을 씁니다. |
| `compile_commands` | `../hal-camera/compile_commands.json` | compile DB 경로. |
| `exclude` | `[]` | 사실에서 뺄 소스 루트 상대 glob. 예: `third_party/**`. |
| `ndk_build.enabled` | `false` | `true`이면 `ndk-build compile_commands.json`으로 DB를 만들고 자동 정규화합니다. |
| `ndk_build.project_dir` | 소스 루트 | `jni/`의 부모(`NDK_PROJECT_PATH`). |
| `ndk_build.args` | `[]` | ndk-build 추가 인자. 예: `["APP_ABI=arm64-v8a"]`. |
| `ndk_build.clang` | DB의 컴파일러 | 내장 헤더 위치를 물을 NDK clang. DB의 컴파일러 이름이 clang이 아니거나 이 머신에 없을 때만 적습니다. |
| `simple_compdb.compiler` | `clang++` | 빌드 시스템 없이 DB를 만들 때의 컴파일러. |
| `simple_compdb.flags` | `[]` | 모든 `.cpp`에 같은 플래그를 붙입니다. 실제 빌드와 `-D`가 다르면 다른 분기를 문서화하므로 시험용으로만 씁니다. |

정규화 동작(상대 경로, `ccache`, `-resource-dir`)은 [첫 실행](../inhouse/02-first-run.md#compile-db가-어떻게-바뀌는가)에 있습니다.

## output과 paths

| 키 | 기본값 | 뜻 |
|---|---|---|
| `output.facts_dir` | `build/facts` | `facts.json` 위치. |
| `output.sdd_dir` | `sdd` | 생성 원고(Markdown)와 승인 장부(`approvals.json`) 위치. |
| `output.diagrams_dir` | `sdd/diagrams` | Mermaid 원문 위치. |
| `paths.sections_file` | `config/sections.yaml` | 문서 정의. [sections.yaml 참조](sections.md). |
| `paths.scenarios_file` | `config/scenarios.yaml` | 시나리오 정의. [scenarios.yaml 참조](sections.md#scenariosyaml). |
| `paths.prompts`, `paths.templates`, `paths.style` | 설정 디렉터리의 `prompts`, `templates`, `style` | 지시문, 페이지 뼈대, 집필 규칙. **설정 디렉터리를 생성기 저장소 밖에 두면 반드시 생성기 저장소의 것을 가리키게 적습니다.** 적지 않으면 생성할 때 파일을 찾지 못합니다. |
| `paths.glossary_file` | 설정 디렉터리의 `config/glossary.yaml` | 용어집. [glossary.yaml 참조](glossary.md). |
| `paths.clang_uml_file` | 설정 디렉터리의 `config/clang-uml.yaml` | clang-uml을 쓸 때의 기본 설정. |

상태 파일(`update-state.json`, `impact.json`, `coverage-triage.json` 등)은 설정 디렉터리의 `build/`에 생깁니다. 목록은 [명령 참조](cli.md#build에-생기는-파일)에 있습니다.

## facts와 tools

| 키 | 기본값 | 뜻 |
|---|---|---|
| `facts.package_depth` | `1` | 패키지 = 선언 파일 경로의 앞 N개 디렉터리. `src/`와 `include/` 아래로만 나뉜 소스는 2~3으로 올립니다. |
| `tools.clang_uml` | `clang-uml` | PATH에 없거나 `none`이면 libclang 대체 분석을 씁니다. |

## agent

문장 설명을 쓰는 모델입니다. 구조(표·그림·시나리오)는 모델 없이 facts에서 만듭니다.

| 키 | 기본값 | 뜻 |
|---|---|---|
| `kind` | `dry-run` | `ollama`, `openai-compatible`, `response-bundle`, `dry-run`. `dry-run`은 모델을 부르지 않고 프롬프트만 `build/prompts/`에 남깁니다. |
| `model` | `qwen3.5:4b` | 모델 이름. |
| `base_url` | `http://localhost:11434` | 엔드포인트. 인증 토큰은 환경 변수 `SDD_AGENT_API_KEY`로만 전달합니다. |
| `max_input_chars` | `18000` | 입력 상한. 넘으면 우선순위 낮은 사실부터 빼고 그 목록을 원고에 남깁니다. |
| `temperature` | `0.1` | 샘플링 온도. |
| `timeout_sec` | `300` | 호출당 제한 시간. |
| `num_ctx` | `0` | Ollama 컨텍스트 창. 0이면 지정하지 않습니다. |
| `think` | `false` | Ollama thinking 모델의 사고 생성. 켜면 호출당 수 분이 더 걸립니다. |
| `max_output_tokens` | `1500` | 출력 상한. 소형 모델의 반복 폭주를 막습니다. |
| `full_style_guides` | `false` | 집필 규칙 전문을 프롬프트에 넣습니다(약 13k자). 소형 모델에서는 끕니다. |
| `response_dir` | 없음 | `response-bundle`의 요청·응답 디렉터리. 설정 파일 기준 상대 경로 또는 절대 경로입니다. |

설정만으로 데이터 반출을 막지는 못합니다. 실제 연결 대상은 운영 환경에서 관리합니다.

`build/prompts/calls/<실행 id>/`에는 호출별 요청·응답·receipt를 보존합니다. 재시도가 같은 출력 디렉터리를 사용해도 기존 호출 기록을 덮어쓰지 않습니다. receipt의 `transport`, `http_call`, 요청·응답 해시, 모델 설정과 공급자가 반환한 토큰 수로 HTTP 호출과 파일 가져오기를 구분합니다. 인증 헤더와 모델의 내부 추론 본문은 receipt에 넣지 않습니다. HTTP 호출 성공이나 해시 일치는 설명의 의미 정확성을 보증하지 않습니다.

### 파일로 LLM 응답 교환하기

`response-bundle`은 네트워크 호출 없이 별도 LLM 실행기가 만든 응답을 같은 생성·검증 경로로 가져옵니다. 생성기는 `<해시>.request.json`을 기록하고 대응하는 `<해시>.response.json`을 읽습니다. 응답이 없으면 기존 원고를 보존하고 실패합니다. 별도 실행기가 응답을 만든 뒤 같은 생성 명령을 다시 실행하세요. 여러 주제는 순서대로 요청되므로 새 요청이 나오면 이 과정을 반복합니다. 이 방식 자체가 LLM을 실행하거나 새 응답을 자동 작성하지는 않습니다. 연결된 모델의 자동 호출에는 `ollama` 또는 `openai-compatible`을 사용합니다.

요청 해시는 `system`, `user`, `response_schema`를 `json.dumps(..., ensure_ascii=False, sort_keys=True)`로 직렬화한 UTF-8의 SHA-256입니다. 응답에는 요청의 `schema`, `model`, `request_sha256`을 그대로 복사하고, `response`에 모델 출력 문자열을 넣습니다. 프롬프트·근거·응답 스키마가 바뀌면 이전 응답을 사용할 수 없습니다. `model`은 생성 주체를 기록하는 이름이며 인증된 신원이나 품질 보증이 아닙니다.

```yaml
agent:
  kind: response-bundle
  model: approved-local-model
  response_dir: build/llm-responses
```

파일에는 원본 소스와 파생 설명이 포함됩니다. 사내 응답 실행기는 사내 보안 경계 안에 두며, 공개 libcamera 응답과 섞지 않습니다. 파일 가져오기에도 인용·필수 질문·본문 지문 검사가 그대로 적용되고 사람 승인 상태는 바뀌지 않습니다.

## review

| 키 | 기본값 | 뜻 |
|---|---|---|
| `require_citations` | `true` | 모델이 쓴 모든 `파일:줄` 인용이 facts에 있어야 통과합니다. |
| `max_retries` | `1` | 검사 실패 시 재시도 횟수. 넘으면 `status: needs-review`로 남깁니다. |
| `design_revision` | `false` | 필수 설계 답변마다 소스와 초안을 다시 보내 수정 답변을 받습니다. 호출 수가 늘며 입력 한도 초과 시 근거를 생략하지 않고 실패합니다. 모델의 재검토는 사람 승인이 아닙니다. |
| `design_grounding` | `false` | 필수 설계 답변을 별도 모델 호출에서 연결된 소스와 대조합니다. 근거 없는 문단이나 누락된 판정은 재시도·실패로 처리합니다. 재사용 지문에 이 설정을 포함하며 자동 판정을 사람 승인으로 표시하지 않습니다. |
| `coverage_triage.enabled` | `false` | 사람이 승인하지 않은 범위 검토 항목을 모델이 먼저 판정합니다. |
| `coverage_triage.pass_gate` | `false` | `true`이면 "범위 밖" 판정이 관문을 통과시킵니다. YAML 불리언만 받습니다. |
| `coverage_triage.agent` | `agent` 값 | 판정 모델만 다르게 할 때 `kind`, `model`, `base_url` 등을 적습니다. `base_url`이 `agent.base_url`과 다르면 토큰은 `SDD_TRIAGE_API_KEY`에서만 읽습니다. |
| `coverage_triage.max_diff_chars` | `6000` | 모델에 보여 줄 diff 상한. |

판정 방식과 위험은 [범위 검사](../concepts/coverage.md#판단을-줄이는-두-단계)에 있습니다.

## documentation

문서 분량·중복·Feature 범위 검사입니다. 개념은 [문서 수명주기](../concepts/document-lifecycle.md)에 있습니다.

| 키 | 기본값 | 뜻 |
|---|---|---|
| `enabled` | `false` | 생성·갱신·게시 전에 검사합니다. |
| `limits.max_chars` | `18000` | 페이지 산문 길이. 표·코드는 세지 않습니다. |
| `limits.max_markdown_chars` | `120000` | 표·코드를 포함한 전체 길이. |
| `limits.max_growth_ratio` | `1.5` | 직전 성공 결과 대비 증가율. |
| `limits.min_growth_chars` | `1000` | 증가율을 따지기 시작하는 최소 증가량. |
| `limits.duplicate_min_chars` | `180` | 중복 문단으로 보는 최소 길이. |
| `pages.<원고>.<한도>` | 없음 | 페이지별 한도. 예: 큰 색인 페이지의 `max_markdown_chars`. |
| `features` | `[]` | Feature별 기준 문서·섹션·시나리오·심볼 계약. |
| `retired_pages` | `[]` | 폐기 계획. |

## diagrams

| 키 | 기본값 | 뜻 |
|---|---|---|
| `enabled` | `false` | prose 섹션에 facts로 만든 클래스 관계 그림을 넣습니다. |
| `max_nodes` | `16` | 그림의 노드 한도. 넘으면 조용히 자르지 않고 실패합니다. 섹션별로 `diagram.max_nodes`로 바꿀 수 있습니다. |
| `direction` | `LR` | Mermaid 방향. |
| `strip_namespace` | `""` | 노드 이름에서 뺄 네임스페이스 접두사. |

## site

| 키 | 기본값 | 뜻 |
|---|---|---|
| `enabled` | `false` | `generate`·`run` 뒤에 사이트 빌드·검증까지 이어서 합니다. |
| `title` | `Camera HAL SDD` | 사이트 이름. |
| `intro` | 없음 | 설정 파일의 디렉터리를 기준으로 한 첫 페이지 안내 Markdown **파일 경로**입니다(예: `intro.md`). 본문 문자열을 넣지 않습니다. |
| `source_url` | 없음 | 인용을 코드로 연결할 저장소 주소. |
| `source_link` | `github` | `github` 또는 `gitiles`. |
| `source_link_template` | 없음 | 그 밖의 코드 열람 도구. 자리표시자 `{url}` `{commit}` `{file}` `{line}`. |
| `mermaid` | 공개 CDN | Mermaid ESM 주소. 사내 문서에서 공개 CDN을 쓰면 외부 코드가 문서 화면에서 실행되므로, 보안 승인 없이 쓰지 않습니다. |
| `mermaid_dir` | 없음 | `sdd fetch-mermaid`로 준비한 사본. 지정하면 사이트에 동봉해 CDN 없이 그립니다. 사내 사이트의 기본 설정입니다. |
| `require_approval` | `false` | 사람 승인 없는 원고가 있으면 게시를 중단합니다. |
| `nav_groups` | `[]` | 왼쪽 메뉴 그룹 순서. |
| `undefined_terms` | 용어집이 있으면 `fail`, 없으면 `warn` | 뜻을 적지 않은 약어의 처리. `fail`, `warn`, `off`. [약어 검사](glossary.md#약어-검사). |
| `english_catalog` | 없음 | 영어판 번역 목록. 공개 libcamera에서만 씁니다. |
| `translation_batch_size` | `1` | 번역 호출당 문장 수. 1~16을 허용하며 입력 예산에 맞게 묶음을 줄입니다. 각 문장의 ID·코드 자리표시자·영어 응답을 검사하고 실패한 묶음은 반영하지 않습니다. |

## update

| 키 | 기본값 | 뜻 |
|---|---|---|
| `compdb_cmd` | 없음 | `sdd update`가 커밋마다 **소스 루트에서** 실행할 compile DB 재생성 명령. `ndk_build.enabled`이면 실행 뒤 자동 정규화합니다. 없을 때 `ndk_build.enabled`이면 `sdd compdb`와 같은 방법(`project_dir`, `args`)으로 다시 만들고, 그 밖에는 기존 DB를 그대로 씁니다. |
| `extract_cmd` | 없음 | 별도 빌드 환경의 추출기를 호출하는 인자 목록. **설정 디렉터리에서** 실행합니다. 생략하면 기존 내장 추출기를 사용합니다. |

외부 추출 명령은 `SDD_SOURCE_COMMIT`, `SDD_SOURCE_ROOT`, `SDD_FACTS_OUTPUT` 환경 변수를 받습니다. 요청된 커밋으로 실제 추출한 facts를 임시 경로인 `SDD_FACTS_OUTPUT`에 저장해야 합니다. 종료 코드가 0이고 출력 파일이 읽히며 `meta.source_commit`이 일치할 때만 기존 facts를 교체합니다. 실패·누락·다른 커밋의 출력은 갱신을 중단하고 기존 facts를 보존합니다. 이후 변경 영향 분석과 LLM 호출·원고 검증은 동일한 `update` 경로를 사용합니다.

Windows의 로컬 Ollama와 WSL의 libcamera 빌드를 연결하는 공개 예제는 [extract_wsl.py](../../examples/libcamera/extract_wsl.py)입니다. 전용 WSL 소스 checkout·Meson 빌드·Linux 설정을 인자로 받으며 원본 checkout을 복원합니다. 이 스크립트는 모델을 호출하거나 저장된 facts를 가져오지 않습니다. 사내 빌드 환경에는 해당 프로젝트의 추출 명령을 연결합니다.

## automation

`sdd automate`의 예약 갱신·게시 설정입니다. 쓰는 법은 [문서 갱신 시스템](../inhouse/03-update-system.md#c-예약-갱신과-게시)에 있습니다.

| 키 | 뜻 |
|---|---|
| `to`, `fetch` | 따라갈 ref, 시작 전 `git fetch` 여부. |
| `schedule.time`, `schedule.timezone`, `schedule.command` | `--cron`이 출력할 예약 시각과 실행 명령. |
| `hermes.enabled`, `hermes.command`, `hermes.timeout_sec`, `hermes.max_input_chars` | 근거가 바뀐 설계 설명을 Hermes가 다시 제안하게 합니다. 승인은 하지 않습니다. |
| `publish.repo`, `publish.directory`, `publish.remote`, `publish.branch` | 사이트를 커밋·push할 문서 저장소. |
| `publish.deploy_command`, `publish.verify_command`, `publish.timeout_sec` | 배포와 실제 URL 확인 명령. 문서 저장소 루트에서 실행하며 `SDD_SOURCE_COMMIT`, `SDD_DOCS_COMMIT`, `SDD_SITE_DIR`, `SDD_BUILD_ID`를 받습니다. |
| `idle_review.enabled`, `sections`, `files`, `source_chars`, `revision` | 새 커밋이 없는 날 기존 문서의 누락을 한 항목씩 보완합니다. `hermes.enabled`가 필요합니다. |

다음 단계: 섹션 정의는 [sections.yaml 참조](sections.md)를 읽습니다.
