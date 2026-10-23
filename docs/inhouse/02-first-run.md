# 2단계: 첫 실행 (NDK-build · legacy HAL3)

**사내 설정 디렉터리를 만들고 아래 4단계를 순서대로 실행하세요.** 각 단계의 확인 값이 맞지 않으면 다음 단계로 넘어가지 않고 [문제 해결](troubleshooting.md)을 봅니다. 처음이면 1시간 정도 걸립니다(추출 시간은 소스 규모에 따라 10~30분).

```
1단계 준비물 → [2단계 첫 실행] → 3단계 갱신 시스템 → 4단계 사람 검토
```

## 1. 설정 디렉터리 만들기

5분 정도 걸립니다.

생성기 저장소 옆에 사내 전용 디렉터리를 둡니다. 사내 클래스명과 설명이 들어가므로 사내 저장소에서 관리합니다.

```text
workspace/
  camera-hal-sdd-generator/   # 생성기 (이 저장소)
  hal-camera-analysis/        # 분석 전용 HAL 체크아웃
  hal-sdd-project/            # 사내 설정과 산출물
    sdd.yaml
    config/sections.yaml
    config/scenarios.yaml
```

`config/sections.yaml`은 생성기 저장소의 `config/sections.yaml`을 복사해 시작합니다.

## 2. sdd.yaml 쓰기

10분 정도 걸립니다.

```yaml
source:
  root: ../hal-camera-analysis
  compile_commands: ../hal-camera-analysis/compile_commands.json
  exclude: ["third_party/**"]
  ndk_build:
    enabled: true
    project_dir: ../hal-camera-analysis
paths:
  prompts: ../camera-hal-sdd-generator/prompts
  templates: ../camera-hal-sdd-generator/templates
  style: ../camera-hal-sdd-generator/style
facts:
  package_depth: 2
agent:
  kind: dry-run          # 모델 없이 먼저 확인합니다. 모델을 쓸 때 openai-compatible 등으로 바꿉니다.
tools:
  clang_uml: none
site:
  enabled: false         # 첫 실행에서는 생성과 사이트 빌드를 나눠 확인합니다.
  source_url: <사내 코드 열람 주소>
  source_link: gitiles
  mermaid_dir: assets/mermaid   # 그림 라이브러리를 사이트에 동봉합니다. 사내 문서가 외부 CDN 코드를 실행하지 않게 합니다.
documentation:
  enabled: true
```

키의 뜻과 기본값은 [설정 참조](../reference/config.md)에 있습니다.

## 3. 무엇을 문서화할지 정하기

30분 이상 걸립니다. 사내 네임스페이스와 진입점 수에 따라 늘어납니다.

1. `config/sections.yaml`의 `facts.classes` 패턴을 사내 네임스페이스로 바꿉니다.
2. 빌드한 모든 클래스·함수가 한 문서에는 실리도록, 복사한 설정의 `components` 섹션을 **구성 요소 색인**으로 바꿉니다. 이 색인이 없으면 문서가 다루지 않는 코드가 바뀔 때마다 갱신이 멈춥니다.

   ```yaml
   - id: components
     kind: per-package
     narration: facts                      # 추가: 모델 없이 패키지별 표만 만듭니다
     facts:
       classes: ['*']
       functions: ['*']                    # 추가: 자유 함수도 싣습니다
     # 나머지 키(title, output, lead, watch 등)는 그대로 둡니다
   ```

3. `config/scenarios.yaml`에 HAL3 진입점을 실제 시그니처로 적습니다. 규칙은 [HAL3 진입점 작성 규칙](../reference/sections.md#hal3-진입점-작성-규칙)에 있습니다.

## 4. 실행하기

20~40분 정도 걸립니다.

생성기 저장소 루트에서 하나씩 실행합니다. 첫 명령은 ndk-build로 compile DB를 만들고 정규화합니다. 새 체크아웃에는 DB가 없으므로 `doctor`보다 먼저 실행합니다.

```bash
uv run sdd --config ../hal-sdd-project/sdd.yaml compdb
```

```bash
uv run sdd --config ../hal-sdd-project/sdd.yaml doctor
```

```bash
uv run sdd --config ../hal-sdd-project/sdd.yaml extract
```

```bash
uv run sdd --config ../hal-sdd-project/sdd.yaml generate
```

Mermaid 사본을 준비합니다. npm에 접근할 수 없는 사내망이면 반입한 파일을 `--tarball mermaid-<버전>.tgz`로 넘깁니다.

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
| `doctor` | 모든 줄이 `[OK]`(clang-uml은 `..`이어도 됩니다) | [문제 해결](troubleshooting.md) |
| `extract` | `파싱 오류 0 개`, `진입점 못 찾음 0 개`, 클래스 수가 HAL 규모와 비슷함 | [문제 해결](troubleshooting.md) |
| `generate` | 원고마다 `status: ok` 또는 `needs-review` | `needs-review`는 [4단계](04-review.md)에서 처리합니다. |
| `verify-site` | `broken_links: 0` | 링크가 깨진 채 게시하지 않습니다. |

결과는 `hal-sdd-project/build/site/index.html`에서 엽니다. 공개 CDN(`site.mermaid` 기본값)은 사내 문서 사이트에서 외부 코드를 실행하게 하므로, 보안 승인을 받은 경우에만 씁니다.

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
