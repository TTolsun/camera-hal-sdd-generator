# 문제 해결

**출력에 나온 문구를 아래 표의 왼쪽 열에서 찾으세요.** 같은 오류로 두 번 실패하면 더 고치지 말고 메시지 원문과 실행한 명령을 기록해 담당자에게 넘깁니다.

## 추출 (`doctor`, `extract`)

| 메시지에 포함된 문구 | 원인 | 조치 |
|---|---|---|
| `Clang 파싱 오류 N개로 추출을 중단합니다` | include 경로, 매크로, 생성 헤더가 빠졌습니다. | 생성 헤더가 디스크에 있는지, 제품 빌드와 같은 `ndk_build.args`로 실행했는지 확인합니다. 추측한 `-I`를 설정에 넣어 통과시키지 않습니다. 다른 변형의 헤더로 파싱될 수 있습니다. |
| `컴파일러가 clang 이 아니라 실행하지 않습니다` | DB의 컴파일러가 wrapper 스크립트입니다. | `source.ndk_build.clang`에 NDK clang 경로를 적습니다. |
| `clang 내장 헤더 위치를 확인하지 못했습니다` | DB에 적힌 clang이 이 머신에 없습니다. | `source.ndk_build.clang`에 이 머신의 NDK clang 경로를 적습니다. |
| `clang 내장 헤더가 없습니다` | 지정한 clang의 resource 디렉터리에 `stddef.h`가 없습니다. | NDK 설치가 완전한지 확인합니다. |
| `ndk-build 를 실행했지만 compile_commands.json 을 찾지 못했습니다` | `project_dir`이 `jni/`의 부모가 아닙니다. | `ndk_build.project_dir`을 `NDK_PROJECT_PATH`로 고칩니다. |
| `응답 파일(@...)을 먼저 풀어야` | DB 인자에 `@파일`이 있습니다. | 응답 파일을 풀어 쓴 DB를 만듭니다. |
| `정규화본을 쓰는 자리` | `source.compile_commands`가 `build/compdb/compile_commands.json`을 가리킵니다. | 원본 DB를 다른 경로에 둡니다. |
| `진입 함수를 정하지 못했습니다: ... (같은 이름의 정의가 N개라 고를 수 없습니다: ...)` | 이름만으로는 하나를 고를 수 없습니다. | 괄호 안 후보 중 하나를 골라 클래스·네임스페이스·인자를 적습니다([작성 규칙](../reference/sections.md#hal3-진입점-작성-규칙)). |
| `진입 함수를 정하지 못했습니다: ... (같은 이름의 함수 정의가 없습니다)` | 이름이 틀렸거나 정의 파일이 DB에 없습니다. | 정의 파일이 `LOCAL_SRC_FILES`에 있는지 확인합니다. |
| `경고: 인자가 다르지만 같은 이름의 정의가 하나뿐이라 사용합니다` | 적은 인자가 실제와 다릅니다. | 추출은 계속됩니다. 출력된 실제 시그니처로 고쳐 둡니다. |

## 생성 (`generate`)

| 메시지에 포함된 문구 | 원인 | 조치 |
|---|---|---|
| `Diagram has N nodes (limit M)` | 섹션이 고른 클래스가 그림 한도를 넘습니다. | `facts.classes`를 좁히거나 그 섹션의 `diagram.max_nodes`를 올립니다. |
| `근거 본문이 변경됐습니다` | 설계 설명이 묶인 소스 발췌가 바뀌었습니다. | [다시 검토하기](04-review.md#설계-설명을-쓰거나-다시-검토하기)를 따릅니다. 해시만 바꾸지 않습니다. |
| `이월하지 못한 원고가 있습니다` | 영향 밖 원고의 인용이 새 facts에 없습니다. | 그 섹션을 다시 생성합니다. |
| `Document lifecycle checks failed` | 페이지 분량·증가율·중복이 한도를 넘었습니다. | `build/document-health.md`의 처리 방향을 따릅니다. 표 위주 페이지는 `documentation.pages`로 한도를 따로 둡니다. |

## 갱신 (`update`)

| 메시지에 포함된 문구 | 원인 | 조치 |
|---|---|---|
| `소스 저장소에 커밋되지 않은 변경이 있습니다` | 분석 체크아웃에 추적되지 않는 파일이 있습니다. | ndk-build가 만든 `compile_commands.json`이면 `.git/info/exclude`에 추가합니다. 다른 파일이면 지우지 말고 누가 만들었는지 확인합니다. |
| `기준 커밋 ... 이 ... 의 조상이 아닙니다` | rebase나 force-push로 기준이 이력에서 사라졌습니다. | 새 이력의 커밋에서 `extract`로 기준을 다시 잡고 `build/update-state.json`을 지운 뒤 실행합니다. |
| `추출된 facts 의 source_commit 이 대상 커밋과 다릅니다` | 체크아웃이 반영되지 않았습니다. | 분석 체크아웃의 권한과 상태를 확인합니다. |
| `LLM 판정: 판단 불가 · 모델 호출에 실패했습니다` | 판정 모델에 연결하지 못했습니다. | 관문은 유지됩니다. 엔드포인트와 토큰(`SDD_TRIAGE_API_KEY` 또는 `SDD_AGENT_API_KEY`)을 확인합니다. |

## 게시 (`export-site`, `verify-site`, `automate`)

| 메시지에 포함된 문구 | 원인 | 조치 |
|---|---|---|
| `broken_links` 0이 아님 | 원고의 링크가 없는 페이지를 가리킵니다. | 원고나 섹션 설정을 고칩니다. 생성된 HTML을 직접 고치지 않습니다. |
| `site.require_approval: 사람 검토 승인이 없는 문서가 있어` | `site.require_approval: true`인데 승인 없는 원고가 있습니다. | [4단계](04-review.md)에서 검토·승인합니다. |
| 그림이 표시되지 않음 | 사내망에서 CDN에 접근할 수 없습니다. | [Mermaid 동봉](02-first-run.md#4-실행하기)을 설정합니다. |
