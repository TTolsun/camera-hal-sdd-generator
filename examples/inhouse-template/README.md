# 사내 HAL 설정 템플릿

기본 설정으로 `generate --sections vendor-contract`를 실행하면 연동 가이드의 설계 질문, 같은 커밋의 발췌, 답변과 그림을 준비합니다. 제품 소스와 빌드 설정, 승인된 CLI가 필요합니다. [첫 실행과 재개](../../docs/inhouse/02-first-run.md)

[반입 패키지 시작 안내](../../docs/inhouse/package.md)에서 시작 프롬프트·실행 순서·합격 기준·복구 절차를 함께 찾을 수 있습니다.

**이 디렉터리를 생성기 저장소 옆에 `hal-sdd-project/`로 복사하고 파일 안의 제품 경로와 빌드 설정을 채우세요.** [첫 실행](../../docs/inhouse/02-first-run.md) 순서대로 facts를 추출하고 원고를 만듭니다.

| 파일 | 채울 것 |
|---|---|
| `sdd.yaml` | `source_url`(코드 열람 주소), 필요하면 `ndk_build.args`, 모델을 쓸 때 `agent` |
| `sdd.cli.local.example.yaml` | 선택한 CLI의 `runner`·`command`·`model`·`args`. `sdd.local.yaml`로 복사하면 적용됩니다. |
| `config/scenarios.yaml` | `<namespace>`와 실제 시그니처, 대조한 정의 위치 |
| `config/glossary.yaml` | 사내 약어의 뜻. `export-site`가 뜻이 없는 약어를 알려 줍니다. |
| `handoff.md` | 단계별 완료·실패·재개 명령과 증거 경로 |
| `config/sections.yaml` | 기존 설계 질문과 직접 지정한 발췌를 유지합니다. 제품별 주제나 클래스 패턴을 추가할 때 수정합니다. |

이 템플릿이 기본으로 켜 둔 것:

1. **ndk-build compile DB 자동 정규화**와 커밋마다 DB 재생성(`ndk_build`의 `project_dir`·`args`를 그대로 씁니다).
2. **구성 요소 색인**(`components` 섹션): 빌드한 모든 클래스·함수를 모델 없이 표로 싣습니다.
3. **Mermaid 동봉**. 사람 승인 없는 문서의 게시 차단(`site.require_approval`)은 첫 실행 뒤 게시 전에 켭니다.
4. **독자 → 수행할 작업 → 문서 메뉴**. `For Vendor`·`For Developer`는 `group`으로 유지하고 작업 소분류는 `config/sections.yaml`의 `nav_section`으로 지정합니다. `generate`·`export-site`가 같은 공통 생성기를 사용하므로 HTML을 따로 편집하지 않습니다.

NDK-build가 아닌 제품의 설정은 [환경별 선택](../../docs/inhouse/agent.md#1-환경과-데이터-경계)을 따릅니다.

## PDF 다운로드 준비

템플릿에는 `site.pdf_downloads: true`가 설정되어 있습니다. 사이트를 빌드하면 독자는 다운로드 메뉴의 **현재 페이지**와 **전체 문서**에서 PDF를 바로 받을 수 있습니다. 아래 명령은 생성기 저장소 루트에서 실행합니다.

1. **빌드 장비에 PDF 렌더러를 설치합니다.** `uv sync --locked --extra dev --extra pdf`로 Playwright와 pikepdf를 설치하고, `uv run --no-sync python -m playwright install chromium --only-shell`로 해당 버전의 Chromium을 준비합니다. 한글을 지원하는 글꼴도 설치하세요. Linux 빌드 이미지에는 Chromium 실행에 필요한 시스템 라이브러리가 있어야 합니다. [Playwright 설치 안내](https://playwright.dev/python/docs/browsers#install-system-dependencies)
2. **Mermaid 본체와 그림 모듈을 함께 준비합니다.** 아래 예시에서 tarball 경로를 반입한 파일 위치로 바꾸세요. 사내 npm 미러에서 받을 때는 `--tarball ../mermaid-11.12.0.tgz` 대신 `--registry <사내 npm 미러 URL>`을 지정합니다. 명령이 끝나면 설정 파일 옆의 `assets/mermaid/`에 `mermaid.esm.min.mjs`와 `chunks/`가 생깁니다.

```bash
uv run --no-sync sdd --config ../hal-sdd-project/sdd.yaml fetch-mermaid --tarball ../mermaid-11.12.0.tgz
```

폐쇄망에서는 반입 패키지의 `requirements-inhouse.txt`로 대상 OS·CPU·Python에 맞는 wheel을 준비합니다. 같은 OS·CPU에서 같은 Playwright 버전으로 설치한 브라우저 캐시도 함께 반입하고, 빌드 계정의 `PLAYWRIGHT_BROWSERS_PATH`를 반입한 캐시 디렉터리로 지정하세요. [폐쇄망 설치 절차](../../docs/inhouse/package.md#반입-확인과-설치)

원고를 생성한 뒤 아래 명령으로 사이트를 빌드하고 검증합니다. 기본 출력은 `../hal-sdd-project/build/site/`이며, 현재 페이지 PDF는 `download/pages/<페이지>.pdf`, 전체 문서 PDF는 `download/full.pdf`에 있습니다.

```bash
uv run --extra pdf sdd --config ../hal-sdd-project/sdd.yaml export-site
uv run --extra pdf sdd --config ../hal-sdd-project/sdd.yaml verify-site
```

## 사내 CLI 선택

사용자가 선택한 Hermes, OpenCode, Claude Code 또는 Codex CLI를 사용합니다. 템플릿의 Codex/Terra High는 저장소의 기본 예시이며 사내 사용의 필수 조건이 아닙니다. 사내에서 Hermes를 사용할 때는 `sdd.cli.local.example.yaml`을 `sdd.yaml` 옆의 `sdd.local.yaml`로 복사합니다. 다른 CLI는 예시의 `runner`를 `opencode`, `claude`, `codex`로 바꾸고 해당 CLI의 모델·인자를 설정합니다. 기존 로컬 파일이 있으면 다른 설정을 보존하고 `agent`만 병합합니다.

`model: ""`, `args: []`, `command: []`는 상속된 모델·인자·실행 경로를 지우고 선택한 CLI의 설정과 PATH를 사용하게 합니다. 로컬 파일에서 키를 생략하는 것만으로는 기본 설정의 값이 제거되지 않습니다. 인증·제공자·모델은 승인된 CLI 설정에서 준비하고 [CLI 선택 안내](../../docs/inhouse/cli-agents.md)에 따라 `doctor`와 실제 호출을 구분해 검증합니다. 호출 없는 점검은 명시적으로 `kind: dry-run`을 지정하며 LLM 생성 성공으로 기록하지 않습니다.

`build/`와 `sdd.local.yaml`만 Git에서 제외합니다. 원고, 승인 장부, Mermaid 사본은 커밋해야 다른 작업 공간에서도 승인과 그림이 유지됩니다.

이 디렉터리를 복사한 사내 저장소에는 사내 클래스명과 설명이 들어가므로, 공개 저장소에 올리지 않습니다.

## 문서 품질을 옮기는 방법

템플릿은 Vendor의 제품 개요·지원 범위와 검증을 **도입 판단**, 연동 가이드를 **연동 구현**으로 묶습니다. Developer는 **구조 이해·코드 탐색·동작 추적과 문제 진단·변경 검토**로 나눕니다. 작업과 문서의 순서는 설정에서 처음 나온 순서를 따릅니다. 장치별 구현 문서는 실제 근거가 있을 때 해당 작업 소분류에 추가하며, libcamera의 장치 이름이나 문서를 사내 기본값으로 복사하지 않습니다. 기존 사내 설정에는 이 항목을 명시적으로 옮겨야 하며 생성기를 교체하는 것만으로 기존 YAML을 자동 수정하지 않습니다.

기본 템플릿의 `first_run_inputs: true`는 비어 있는 LLM 주제에 적용됩니다. `build/first-run-inputs.json`에서 구체화한 질문과 선택된 발췌를 확인하세요. 생성 결과를 읽을 때는 독자가 어떤 상태를 확인하고 다음에 어떤 행동을 할 수 있는지 대조합니다. 직접 설정한 주제와 고정 계약은 [계약 작성 절차](../../docs/inhouse/contract-authoring.md)를 따릅니다.

[공통 품질 기준과 읽기 검증](../../docs/concepts/reader-quality.md), [완성된 작은 HAL 예제](../mini-hal/config/reader-sections.yaml)를 따라 작성하세요. 소스 근거 고정과 필수 질문 검사는 libcamera와 같은 생성기를 사용합니다. 실제 사내 HAL의 동작과 설명은 사내 독자가 별도로 검토해야 합니다.
