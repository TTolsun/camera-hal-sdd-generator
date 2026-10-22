# NDK-build·legacy HAL3 HAL에서 설계 문서 만들기

**`source.ndk_build.enabled: true`로 설정하고 `sdd doctor` → `sdd extract` 순서로 실행한 뒤, `파싱 오류 0 개`와 `진입점 못 찾음 0 개`를 확인하세요.** 두 값이 0이 아니면 다음 단계로 넘어가지 않습니다.

이 문서는 사내 Camera HAL처럼 NDK-build로 빌드하고 legacy HAL3(`camera3_*`) 인터페이스를 쓰는 소스에 생성기를 적용하는 절차입니다. 공통 절차는 [사내 적용 절차](inhouse-adoption.md)에 있고, 이 문서는 NDK-build와 HAL3 때문에 달라지는 부분만 다룹니다.

**이 절차는 실제 NDK와 사내 소스로 실행되지 않았습니다.** 원본 compile DB의 모양과 HAL3 ops·콜백 구조는 [`tests/test_ndk_hal3.py`](../tests/test_ndk_hal3.py)에서 재현해 검사합니다. 사내에서 처음 실행한 뒤 어긋난 부분을 이 문서에 반영해야 합니다.

| 지금 확인할 내용 | 이동할 절 |
|---|---|
| 무엇을 준비해야 하는지 확인합니다. | [1. 준비물](#1-준비물) |
| 설정 파일을 작성합니다. | [2. 설정](#2-설정) |
| 명령을 순서대로 실행합니다. | [3. 실행 순서](#3-실행-순서) |
| compile DB가 어떻게 바뀌는지 이해합니다. | [4. compile DB 정규화](#4-compile-db-정규화) |
| 시나리오 진입점을 적습니다. | [5. HAL3 진입점 작성](#5-hal3-진입점-작성) |
| 오류 메시지별 조치를 찾습니다. | [6. 문제 해결](#6-문제-해결) |
| 커밋마다 갱신합니다. | [7. 증분 갱신](#7-증분-갱신) |

## 1. 준비물

| 항목 | 확인할 내용 |
|---|---|
| HAL 소스와 고정 SHA | 문서의 모든 인용이 이 SHA의 파일과 줄을 가리킵니다. 분석 전용 체크아웃을 따로 둡니다. `sdd update`는 커밋마다 소스를 체크아웃하기 때문입니다. |
| NDK | 제품 빌드와 같은 버전을 씁니다. r25 이상을 권장합니다. 그 이하는 `compile_commands.json`의 인자 escaping이 불안정합니다. |
| `ndk-build`가 PATH에 있는 환경 | 생성기가 `ndk-build compile_commands.json`을 직접 실행합니다. 이 명령은 빌드하지 않고 DB만 만듭니다. |
| Python 3.11 이상과 `uv` | `uv sync --extra dev`로 libclang 18.1.1이 함께 설치됩니다. |
| 생성 헤더 | 빌드 중에 만들어지는 헤더가 있다면, 먼저 한 번 빌드해서 그 헤더가 디스크에 있어야 합니다. 없으면 파싱 오류가 납니다. |

## 2. 설정

### sdd.yaml

사내 설정 디렉터리에 둡니다. 상대 경로는 이 파일 기준입니다.

```yaml
source:
  root: ../hal-camera-analysis              # 분석 전용 HAL 체크아웃
  compile_commands: ../hal-camera-analysis/compile_commands.json
  exclude: ["third_party/**"]
  ndk_build:
    enabled: true
    project_dir: ../hal-camera-analysis     # jni/ 의 부모 (NDK_PROJECT_PATH)
    args: []                                # 예: ["APP_ABI=arm64-v8a", "NDK_DEBUG=0"]
    # clang: /opt/android-ndk-r27/toolchains/llvm/prebuilt/linux-x86_64/bin/clang++

update:
  compdb_cmd: ["ndk-build", "compile_commands.json"]
```

`clang`은 보통 비워 둡니다. 생성기가 DB에 적힌 NDK clang으로 내장 헤더 위치를 찾습니다. 다음 경우에만 적습니다.

- DB를 만든 머신과 추출하는 머신이 달라서, DB에 적힌 clang 경로가 추출하는 머신에 없을 때
- 컴파일러 이름이 `clang`, `clang++`, `clang-18` 같은 형태가 아닐 때 (예: 사내 wrapper 스크립트)

### config/scenarios.yaml

HAL3 진입점의 **실제 시그니처**를 적습니다. 작성 규칙은 [5절](#5-hal3-진입점-작성)에 있습니다.

```yaml
defaults:
  glob: ["**/*.cpp"]
  depth: 5
  hide:
    names: ["ALOG*", "ATRACE*"]   # 로깅·트레이스 호출이 흐름을 덮지 않게 숨긴다

scenarios:
  - id: process_capture_request
    title: 캡처 요청 처리
    from: "vendor::camera::CameraDevice::processCaptureRequest(camera3_capture_request_t *)"
    # 정의: device/CameraDevice.cpp:120   # 대조한 위치를 적어 둔다
    depth: 6
  - id: flush
    title: 플러시
    from: "vendor::camera::CameraDevice::flush()"
```

### 소스 저장소의 Git 상태

`ndk-build compile_commands.json`은 `project_dir`에 `compile_commands.json`을 씁니다. 이 파일이 HAL 저장소 안에 생기고 Git이 추적하지 않는 파일이면, `sdd update`는 "소스 저장소에 커밋되지 않은 변경이 있습니다"라며 시작하지 않습니다. 분석 전용 체크아웃의 `.git/info/exclude`에 `compile_commands.json`을 한 줄 추가합니다. 이 파일은 로컬에만 적용되므로 HAL 저장소에 커밋되지 않습니다.

## 3. 실행 순서

생성기 저장소 루트에서 실행합니다.

```bash
uv run sdd --config ../hal-sdd-project/sdd.yaml doctor
```

```bash
uv run sdd --config ../hal-sdd-project/sdd.yaml extract
```

```bash
uv run sdd --config ../hal-sdd-project/sdd.yaml generate
```

```bash
uv run sdd --config ../hal-sdd-project/sdd.yaml export-site
```

```bash
uv run sdd --config ../hal-sdd-project/sdd.yaml verify-site
```

각 단계에서 아래 값을 확인합니다. 기대와 다르면 다음 단계로 넘어가지 않습니다.

| 단계 | 확인할 값 | 어긋나면 |
|---|---|---|
| `doctor` | compile DB 경고가 없습니다. | sysroot 경로가 없다는 경고는 NDK 설치 위치를 확인합니다. |
| `extract` | `[comments] ... 파싱 오류 0 개` | [6절](#6-문제-해결)에서 메시지를 찾습니다. |
| `extract` | `[callgraph] ... 진입점 못 찾음 0 개` | [5절](#5-hal3-진입점-작성)의 규칙으로 시그니처를 고칩니다. |
| `extract` | 클래스 수가 HAL 규모와 맞습니다. | `exclude`와 DB의 TU 수(`translation_units`)를 확인합니다. |
| `generate` | `status: needs-review` 페이지 목록 | 각 페이지의 근거 블록에 사유가 있습니다. |
| `verify-site` | `broken_links: 0` | 링크가 깨진 채로 게시하지 않습니다. |

## 4. compile DB 정규화

ndk-build가 만든 원본 DB는 libclang이 그대로 읽지 못합니다. 생성기는 이 DB를 자동으로 정규화하므로 `sdd compdb --normalize`를 따로 실행하지 않아도 됩니다.

### 원본 DB를 그대로 쓰면 실패하는 이유

1. **상대 경로를 씁니다.** `-Ijni`, `"file": "jni/CameraDevice.cpp"`처럼 `LOCAL_PATH` 기준으로 적습니다. libclang은 DB의 `directory`로 이동하지 않으므로 헤더를 찾지 못합니다.
2. **wrapper가 붙을 수 있습니다.** `NDK_CCACHE`를 쓰면 `ccache clang++ ...` 형태가 됩니다. 이대로 넘기면 `clang++` 경로가 입력 파일로 해석됩니다.
3. **내장 헤더가 없습니다.** pip로 설치한 libclang에는 `stddef.h` 같은 clang 내장 헤더가 없습니다. NDK clang의 내장 헤더 위치를 `-resource-dir`로 알려 줘야 합니다.

libcamera에서도 Meson DB를 그대로 넘겨 TU 171개가 전부 파싱에 실패했습니다.

### 정규화 흐름

```
ndk-build compile_commands.json
        │  (project_dir 에 원본 DB)
        ▼
원본 DB ── 고치지 않음 (소스 저장소의 작업 트리를 바꾸지 않기 위해)
        │
        ├─ ccache·sccache 등 wrapper 제거
        ├─ -I·file·--sysroot 를 절대 경로로, -working-directory 추가
        ├─ DB 의 NDK clang -print-resource-dir ──► -resource-dir 추가
        │      (이름이 clang 이 아니면 실행하지 않고 중단)
        ▼
정규화본: source.compile_commands 가 원본을 가리키면 build/compile_commands.ndk.json
        ▼
libclang 파싱
```

정규화는 다음 세 시점에 일어납니다.

1. `sdd compdb`나 `sdd extract`가 `ndk-build compile_commands.json`을 실행한 직후
2. `source.compile_commands`가 아직 정규화되지 않은 원본 DB를 가리킬 때 (사람이나 CI가 ndk-build를 직접 실행한 경우)
3. `sdd update`가 `update.compdb_cmd`를 실행한 직후

모든 항목에 `-working-directory`와 `-resource-dir`가 있어야 정규화된 DB로 봅니다. 일부 항목만 정규화된 DB는 다시 정규화합니다.

### 주의할 점

- **clang 버전 차이**: pip libclang은 18.1.1입니다. NDK clang의 주 버전이 크게 다르면 내장 헤더가 맞지 않을 수 있습니다. 사내 NDK 버전으로 `파싱 오류 0 개`를 확인해야 합니다.
- **응답 파일**: DB 인자에 `@파일.rsp`가 있으면 정규화를 거부합니다. 응답 파일을 풀어 쓴 DB가 필요합니다.
- **빌드 변형**: `APP_ABI`나 제품별 `-D` 매크로가 다르면 변형마다 설정과 출력 디렉터리를 따로 둡니다. 생성기는 한 DB 안에서 같은 이름의 매크로 값이 다르면 처음 값만 기록합니다.

## 5. HAL3 진입점 작성

### 핵심 규칙

1. **클래스와 네임스페이스까지 적습니다.** `vendor::camera::CameraDevice::flush()`처럼 완전한 이름으로 적으면, 접미사가 같은 다른 네임스페이스의 정의보다 우선합니다.
2. **인자 타입을 소스와 같게 적습니다.** 인자 이름은 적지 않습니다. 공백 차이는 무시합니다.
3. **`struct` 표기 차이는 같은 시그니처로 취급합니다.** 헤더가 `const struct camera3_device *`라고 적었어도 `const camera3_device *`로 적을 수 있습니다.
4. **모호하면 추출이 멈춥니다.** 같은 이름의 정의가 여럿이고 시그니처로 하나를 고를 수 없으면, 후보 목록을 출력하고 추출을 중단합니다. 기존 facts와 그림은 그대로 남습니다.

이렇게 엄격하게 처리하는 이유는 엉뚱한 함수에서 시작한 시나리오가 문서에 조용히 실리는 것을 막기 위해서입니다. HAL3 코드에는 `flush`, `close`처럼 같은 이름의 함수가 여러 클래스에 있습니다.

### ops 표의 trampoline에서 시작하기

legacy HAL3는 `camera3_device_ops` 함수 포인터 표로 framework와 연결됩니다. 표에 등록한 정적 함수가 `dev->priv`를 캐스트해서 멤버 함수를 부르는 구조가 일반적입니다.

```cpp
int CameraDevice::sProcessCaptureRequest(const struct camera3_device *dev,
                                         camera3_capture_request_t *request) {
    return static_cast<CameraDevice *>(dev->priv)->processCaptureRequest(request);
}
```

이 경우 진입점은 둘 중 하나로 적을 수 있습니다.

| 진입점 | 문서에 보이는 흐름 |
|---|---|
| `...::CameraDevice::sProcessCaptureRequest(const camera3_device *, camera3_capture_request_t *)` | framework 진입 지점부터 시작합니다. 첫 단계가 `processCaptureRequest` 호출입니다. |
| `...::CameraDevice::processCaptureRequest(camera3_capture_request_t *)` | HAL 내부 처리부터 시작합니다. 단계를 하나 아낍니다. |

### framework 콜백은 경계로 남습니다

HAL이 결과를 돌려줄 때 부르는 `camera3_callback_ops`의 `process_capture_result`와 `notify`는 함수 포인터 호출입니다. 문서에는 "함수 포인터, 정적 추적 불가"로 표시됩니다. 이것은 HAL에서 framework로 돌아가는 경계이며, 그 뒤의 처리는 HAL 문서의 대상이 아닙니다.

마찬가지로 큐에 넣고 다른 스레드가 꺼내 처리하는 흐름은 정적 호출로 이어지지 않습니다. 워커 스레드의 처리 함수를 별도 시나리오의 진입점으로 등록합니다. [mini-hal 예제](../examples/mini-hal/config/scenarios.yaml)의 `frame_processing`이 이 방식입니다.

## 6. 문제 해결

| 메시지 | 원인 | 조치 |
|---|---|---|
| `Clang 파싱 오류 N개로 추출을 중단합니다` | include 경로, 매크로, 생성 헤더가 빠졌습니다. | 생성 헤더가 디스크에 있는지 확인합니다. 제품 빌드와 같은 `args`로 ndk-build를 실행했는지 확인합니다. |
| `compile DB 의 컴파일러가 clang 이 아니라 실행하지 않습니다` | DB의 컴파일러가 wrapper 스크립트입니다. | `source.ndk_build.clang`에 NDK clang 경로를 적습니다. |
| `clang 내장 헤더 위치를 확인하지 못했습니다` | DB에 적힌 clang이 이 머신에 없습니다. | `source.ndk_build.clang`에 이 머신의 NDK clang 경로를 적습니다. |
| `clang 내장 헤더가 없습니다` | 지정한 clang의 resource 디렉터리에 `stddef.h`가 없습니다. | NDK 설치가 완전한지 확인합니다. |
| `ndk-build 를 실행했지만 compile_commands.json 을 찾지 못했습니다` | `project_dir`이 `jni/`의 부모가 아닙니다. | `project_dir`을 `NDK_PROJECT_PATH`로 고칩니다. |
| `응답 파일(@...)을 먼저 풀어야` | DB 인자에 `@파일`이 있습니다. | 응답 파일을 풀어 쓴 DB를 만듭니다. |
| `진입 함수를 정하지 못했습니다: ... (같은 이름의 정의가 N개라 고를 수 없습니다: ...)` | 이름만으로는 하나를 고를 수 없습니다. | 괄호 안의 후보 중 하나를 골라 클래스·네임스페이스·인자를 적습니다. |
| `진입 함수를 정하지 못했습니다: ... (같은 이름의 함수 정의가 없습니다)` | 이름이 틀렸거나, 정의가 있는 파일이 DB에 없습니다. | 정의 파일이 `LOCAL_SRC_FILES`에 있는지 확인합니다. |
| `경고: 인자가 다르지만 같은 이름의 정의가 하나뿐이라 사용합니다` | 적은 인자가 실제와 다르지만 후보가 하나입니다. | 추출은 계속됩니다. 출력된 실제 시그니처로 고쳐 둡니다. |
| `소스 저장소에 커밋되지 않은 변경이 있습니다` (`sdd update`) | ndk-build가 만든 `compile_commands.json`이 추적되지 않는 파일로 남았습니다. | [2절](#소스-저장소의-git-상태)처럼 `.git/info/exclude`에 추가합니다. |

## 7. 증분 갱신

첫 생성을 사람이 검토한 뒤에는 커밋 단위로 갱신합니다.

```bash
uv run sdd --config ../hal-sdd-project/sdd.yaml update --to origin/main
```

`update.compdb_cmd`가 있으면 커밋마다 ndk-build로 DB를 다시 만들고 정규화합니다. `Android.mk`가 바뀐 커밋에서 낡은 DB로 추출하면 사실이 어긋나므로, NDK 프로젝트에서는 이 설정을 둡니다.

| 종료 코드 | 뜻 | 다음 행동 |
|---|---|---|
| 0 | 새 커밋을 모두 처리했습니다. | `export-site`와 `verify-site`를 실행합니다. |
| 1 | 한 커밋의 처리가 실패했습니다. | 로그의 원인을 해결하고 같은 명령을 다시 실행합니다. 같은 커밋부터 재시도합니다. |
| 2 | 승인되지 않은 범위 검토 항목이 있습니다. | `build/impact-review.md`를 검토하고 `sdd accept --finding <키>`로 기록합니다. |
| 3 | `needs-review` 페이지가 있습니다. | 사람이 검토한 뒤 `sdd accept <문서>`로 기록합니다. |

자동 검사 통과는 사람 승인이 아닙니다. `sdd accept`는 사람이 실제로 검토한 뒤에만 실행합니다.

## 근거와 검토 정보

- 정규화 규칙: [`src/sdd/compdb.py`](../src/sdd/compdb.py)의 `normalize_ndk`, `normalize`, `is_normalized`
- 진입점 선택 규칙: [`src/sdd/facts/callgraph.py`](../src/sdd/facts/callgraph.py)의 `match_entry`
- 재현 테스트: [`tests/test_ndk_hal3.py`](../tests/test_ndk_hal3.py)
- 사내 LLM 에이전트가 이 절차를 따르게 하려면 [SDD 생성 스킬](../skills/camera-hal-sdd/SKILL.md)을 설치합니다.

다음 단계: 사내 설정 디렉터리에 [2절](#2-설정)의 `sdd.yaml`을 만들고 `sdd doctor`를 실행합니다.
