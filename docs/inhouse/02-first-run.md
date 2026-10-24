# 2단계: 첫 실행 (NDK-build · legacy HAL3)

**사내 설정 템플릿을 복사하고 아래 4단계를 순서대로 진행하세요.** 각 단계의 확인 값이 맞지 않으면 다음 단계로 넘어가지 않고 [문제 해결](troubleshooting.md)을 봅니다. 처음이면 1시간 정도 걸립니다(추출 시간은 소스 규모에 따라 10~30분).

```
1단계 준비물 → [2단계 첫 실행] → 3단계 갱신 시스템 → 4단계 사람 검토
```

## 1. 설정 디렉터리 만들기

5분 정도 걸립니다. 생성기 저장소의 [사내 설정 템플릿](../../examples/inhouse-template/)을 생성기 저장소 옆으로 복사합니다. 사내 클래스명과 설명이 들어가므로 이 디렉터리는 사내 저장소에서 관리합니다.

```text
workspace/
  camera-hal-sdd-generator/   # 생성기 (이 저장소)
  hal-camera-analysis/        # 분석 전용 HAL 체크아웃
  hal-sdd-project/            # examples/inhouse-template 을 복사한 곳
```

## 2. sdd.yaml 채우기

10분 정도 걸립니다. 복사한 `sdd.yaml`에서 `<...>`로 표시한 칸을 채웁니다.

1. `site.source_url`: 인용을 연결할 사내 코드 열람 주소. Gitiles가 아니면 `source_link`도 바꿉니다.
2. `source.ndk_build.args`: 제품 빌드와 같은 ndk-build 인자.
3. 경로가 위 배치와 다르면 `source.root`, `ndk_build.project_dir`, `paths.*`를 고칩니다.

템플릿은 모델 없이(`agent.kind: dry-run`) 시작하고, Mermaid 동봉과 승인 없는 문서의 게시 차단을 켜 둡니다. 키의 뜻은 [설정 참조](../reference/config.md)에 있습니다.

## 3. 무엇을 문서화할지 정하기

30분 이상 걸립니다. 사내 네임스페이스와 진입점 수에 따라 늘어납니다.

1. `config/scenarios.yaml`의 `<namespace>`와 시그니처를 실제 정의로 바꿉니다. 규칙은 [HAL3 진입점 작성 규칙](../reference/sections.md#hal3-진입점-작성-규칙)에 있습니다.
2. `config/sections.yaml`의 `overview`·`threading` 클래스 패턴을 사내 이름에 맞춥니다. 그대로 두어도 동작합니다.
3. `config/glossary.yaml`에 사내 약어(칩·블록·모듈 이름)의 뜻을 적습니다. 미리 다 채우지 않아도 됩니다. 4단계의 `export-site`가 뜻이 없는 약어와 문서를 알려 주고 게시를 멈추므로, 그 목록을 채웁니다. 형식은 [glossary.yaml 참조](../reference/glossary.md)에 있습니다.
4. `components` 섹션은 **구성 요소 색인**으로 켜 두었습니다(`narration: facts`, 클래스·함수 `'*'`). 빌드한 모든 코드가 한 문서에 실리므로, 문서가 다루지 않는 코드가 바뀔 때마다 갱신이 멈추는 일이 크게 줄어듭니다. 끄지 않습니다.

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
| `export-site` | `뜻을 적지 않은 약어` 오류가 없음 | 나온 약어를 `config/glossary.yaml`에 추가합니다. [약어 검사](../reference/glossary.md#검사가-실패하면) |
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
