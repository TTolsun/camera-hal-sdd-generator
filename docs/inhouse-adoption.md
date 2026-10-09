# 사내 Camera HAL 적용 절차

**먼저 [필요한 입력](#1-필요한-입력)을 확보하고 [바꿀 설정](#2-바꿀-설정)을 실제 환경에 맞춘 뒤 [실행 순서](#3-실행-순서)를 따르세요.**

사내 Claude에 초기 구축과 CI 연결을 맡기려면 [복사용 지시문과 구축 가이드](inhouse-agent-bootstrap.md)를 사용하세요.

이 문서는 libcamera 공개 검증에서 확인한 파이프라인을 사내 Camera HAL에 옮기는 절차입니다. **사내 소스와 빌드 구성을 아직 받지 못했으므로 여기 적은 절차는 실행으로 검증되지 않았습니다.** libcamera에서 확인한 동작과 사내에서 확인해야 할 항목을 구분해서 적습니다.

| 지금 확인할 내용 | 이동할 절 |
|---|---|
| 사내에서 무엇을 받아야 하는지 확인합니다. | [필요한 입력](#1-필요한-입력) |
| 어떤 설정을 고쳐야 하는지 확인합니다. | [바꿀 설정](#2-바꿀-설정) |
| 어떤 명령을 어떤 순서로 실행하는지 확인합니다. | [실행 순서](#3-실행-순서) |
| 환경 없이 지금 할 수 있는 일을 찾습니다. | [환경 없이 준비할 수 있는 것](#4-환경-없이-준비할-수-있는-것) |
| 사내에서만 확인할 수 있는 위험을 봅니다. | [사내에서 확인해야 하는 것](#5-사내에서-확인해야-하는-것) |

## 1. 필요한 입력

아래 입력을 단계별로 확인합니다. 필요한 입력이 없는 단계는 미완료로 남기고, 독립적으로 수행할 수 있는 준비 작업을 계속합니다.

1. **HAL 소스와 고정할 SHA.** 문서의 모든 인용이 이 SHA의 파일과 줄을 가리킵니다. 움직이는 브랜치 이름을 기준으로 삼으면 인용이 어긋납니다.
2. **`compile_commands.json`.** NDK-build나 AOSP 빌드가 만든 것이어야 합니다. 실제 제품의 include 경로, `-D` 매크로, 생성 헤더가 들어 있어야 합니다. 이것이 없으면 파싱이 전부 실패합니다.
3. **생성 방식과 선택적 LLM 엔드포인트.** 소스 계약과 facts 기반 문서는 생성 시 LLM 호출이 필요하지 않습니다. LLM 초안을 사용할 때는 허용된 사내 엔드포인트의 주소·모델·인증 방법을 확인합니다.
4. **정적 자산과 게시 위치.** Mermaid 기본 주소는 공개 CDN입니다. 외부 접근이 제한된 환경에서는 `site.mermaid_dir`로 자산을 동봉하거나 `site.mermaid`를 사내 경로로 지정합니다.

## 2. 바꿀 설정

먼저 아래 설정과 사내 자산 위치를 맞춥니다. 실제 소스를 분석하기 전에는 설정 변경만으로 적용이 끝난다고 단정하지 않습니다.

### sdd.yaml

```yaml
source:
  root: ../hal-camera                    # 사내 HAL 소스 루트
  compile_commands: ../hal-camera/compile_commands.json
  exclude: []                            # third_party 헤더처럼 사실에서 뺄 경로
  ndk_build:
    enabled: true
    project_dir: ../hal-camera

facts:
  package_depth: 1                       # 패키지가 두세 개로 뭉치면 2 나 3 으로 올린다

agent:
  kind: openai-compatible                # 사내 게이트웨이를 쓸 때
  base_url: https://<사내 엔드포인트>
  model: <모델 이름>

site:
  enabled: true
  title: Camera HAL 설계 문서
  source_url: <사내 코드 열람 주소>       # 인용을 코드로 연결할 주소
  source_link: gitiles                   # Gerrit Gitiles 는 gitiles, GitHub/GHE 는 github(기본)
  # source_link_template: "{url}/browse/{file}?at={commit}#{line}"   # 그 밖의 호스트
  mermaid_dir: assets/mermaid            # sdd fetch-mermaid 가 준비한 사본을 사이트에 동봉
  require_approval: true                 # 사람 검토 승인 없는 문서는 게시 중단
  nav_groups: ["시작하기", "For Users", "For Developers"]
```

`package_depth`는 libcamera에서 실제로 문제가 됐던 값입니다. 소스가 `src/`와 `include/` 아래로만 나뉘면 기본값 1은 패키지를 세 개로 뭉쳐서 개요의 패키지 표가 쓸모없어집니다. 추출 후 `facts.json`의 `packages` 개수를 보고 정합니다.

`documentation.enabled: true`로 [문서 수명주기 검사](document-lifecycle.md)를 켜고, Feature별 기준 문서와 필수 섹션·시나리오·심볼을 등록합니다. 분량 한도는 실제 HAL 문서를 읽으며 조정합니다. 분리·통합·폐기 판단은 근거를 보존한 상태에서 검토하고, `audit-docs` 실패가 CI와 게시를 중단하는지 확인하세요.

인용 링크 형식은 `source_link`(github·gitiles) 또는 `source_link_template`으로 코드 열람 도구에 맞춥니다. 템플릿의 자리표시자는 `{url}` `{commit}` `{file}` `{line}` 네 개이며, 어긋난 템플릿은 export-site 가 즉시 거부합니다.

### config/scenarios.yaml

HAL3 진입점의 **실제 시그니처**로 바꿉니다. 현재 값은 예시입니다.

```yaml
scenarios:
  - id: process_capture_request
    title: 캡처 요청 처리 (processCaptureRequest)
    from: "CameraDevice::processCaptureRequest(camera3_capture_request_t *)"
    # 정의: <파일>:<줄>                  # 대조한 위치를 적어 둔다
    depth: 5
```

libclang 경로에서 시그니처에 맞는 진입점을 찾지 못하면 `extract`가 실패하고 기존 facts를 보존합니다. 파싱 오류나 빈 compile DB도 같은 방식으로 중단합니다. 생성 단계에서도 설정된 시나리오가 facts에 빠져 있으면 목차를 `needs-review`로 표시합니다.

로깅 매크로가 호출 그래프의 대부분을 차지하면 `defaults.hide`에 이름을 적습니다. libcamera에서는 `LOG()` 매크로와 d-pointer 접근자가 첫 30단계 중 22단계를 차지했습니다. 사내 HAL은 `ALOGD` 계열이 같은 자리에 올 가능성이 높습니다.

```yaml
defaults:
  hide:
    owners: ["Log", "Trace"]
    names: ["ALOG*", "_d"]
```

### config/sections.yaml

`facts.classes`와 `facts.functions`의 패턴을 사내 네임스페이스로 바꿉니다. 현재 값은 `camera_*`, `HAL_*` 같은 예시입니다. `group` 값은 독자 기준으로 이미 나뉘어 있으므로 그대로 두거나 사내 용어로 바꿉니다.

설계 내용을 설명할 페이지에는 `design_requirements`로 필수 질문을 정의하고, `design_topics`의 설명에 `covers`와 `evidence`를 연결합니다. 실제 HAL 구현을 대조하여 질문·답변·근거 발췌를 작성해야 하며 libcamera의 설명과 해시를 그대로 사용하지 않습니다. [설계 근거 검사](design-evidence.md)의 설정 예시를 참고하세요.

### 사내 자산

Mermaid ESM 배포본은 `sdd fetch-mermaid`로 준비합니다. 본체와 chunk 모듈을 함께 가져와야 그림이 뜨며, 이 명령이 그 구조를 만들어 줍니다.

```bash
uv run sdd --config <사내설정>/sdd.yaml fetch-mermaid                       # npm 접근이 되는 곳에서
uv run sdd --config <사내설정>/sdd.yaml fetch-mermaid --tarball mermaid-11.12.0.tgz   # 망 분리 반입
```

위의 `site.mermaid_dir` 설정을 두면 export-site 가 이 사본을 사이트 산출물의 `assets/mermaid/`로 복사해 동봉하므로, 페이지에 CDN 주소가 남지 않습니다. 이미 사내 웹 서버에 호스팅한 주소가 있으면 `site.mermaid`로 그 주소만 지정해도 됩니다. 지정하지 않으면 `https://cdn.jsdelivr.net/npm/mermaid@11/...`을 그대로 씁니다. 엔드포인트 설정만으로 외부 통신이 차단되는 것은 아니므로, 실행 환경의 통신 경계도 함께 확인해야 합니다.

## 3. 실행 순서

```bash
uv run sdd --config <사내설정>/sdd.yaml doctor
uv run sdd --config <사내설정>/sdd.yaml extract
uv run sdd --config <사내설정>/sdd.yaml generate
uv run sdd --config <사내설정>/sdd.yaml export-site
uv run sdd --config <사내설정>/sdd.yaml verify-site
```

각 단계에서 확인할 숫자입니다. 기대와 다르면 다음 단계로 넘어가지 않습니다.

| 단계 | 확인할 값 | 어긋나면 |
|---|---|---|
| `extract` | 파싱 오류 0 개 | compile DB의 include 경로와 생성 헤더를 확인합니다. |
| `extract` | 진입점 못 찾음 0 개 | `scenarios.yaml`의 시그니처를 정의와 대조합니다. |
| `extract` | 클래스 수가 소스 규모와 맞는가 | 파싱은 됐지만 범위가 좁으면 `exclude`와 compile DB의 translation unit 수를 봅니다. |
| `generate` | `status: needs-review` 페이지 목록 | 사유가 각 페이지의 근거 블록에 적혀 있습니다. |
| `verify-site` | `broken_links: 0` | 링크가 깨진 채로 게시하지 않습니다. |

compile DB 는 빌드 시스템별로 이렇게 확보합니다.

| 빌드 시스템 | 확보 방법 |
|---|---|
| NDK-build | `sdd compdb` (`source.ndk_build.enabled: true`) |
| Soong (AOSP) | `SOONG_GEN_COMPDB=1 SOONG_GEN_COMPDB_DEBUG=1 m nothing` 후 `out/soong/development/ide/compdb/compile_commands.json` |
| CMake | `-DCMAKE_EXPORT_COMPILE_COMMANDS=ON` |
| Meson | 빌드 디렉터리에 `compile_commands.json` 생성됨 |

어느 빌드가 만든 DB든 그대로 넘기면 상대 경로와 clang 내장 헤더 때문에 파싱이 전부 실패할 수 있습니다(libcamera 실측: TU 171개 전부 실패). `sdd compdb --normalize`가 경로를 절대 경로로 바꾸고 `-working-directory`를 채우며, `--clang <실행 파일>`을 주면 `-resource-dir`도 채웁니다. 정규화본은 원본과 별도 파일로 쓰고 `source.compile_commands`가 그 파일을 가리키게 합니다.

```bash
uv run sdd --config <사내설정>/sdd.yaml compdb --normalize --normalize-input <빌드출력>/compile_commands.json --clang clang --out <사내설정>/build/compile_commands.json
```

Windows에서 Meson이나 NDK 빌드가 어려우면 libcamera 검증과 같은 방식을 씁니다. Linux에서 추출까지 수행하고 `facts.json`을 옮긴 뒤, LLM 호출이 가능한 환경에서 생성합니다. clang-uml 은 없어도 libclang 대체 분석으로 동작하며(`doctor`가 경고로 알림), 그 경우 템플릿 관계·조건 분기·include 그래프가 빠집니다.

`design_topics`를 사용하는 생성 단계는 고정 커밋의 Git 소스에서 근거를 다시 수집합니다. 따라서 이 방식으로 환경을 나누더라도 생성 환경에서 해당 커밋과 파일을 읽을 수 있어야 합니다. facts만 옮기고 소스 저장소를 연결하지 않으면 설계 근거 수집을 완료할 수 없습니다.

### 반복 운영: 승인과 증분 갱신

첫 전체 생성이 끝난 뒤에는 커밋 단위로 반복합니다.

1. **증분 갱신.** `sdd update --to <브랜치>`가 마지막으로 처리한 커밋 이후의 커밋을 오래된 것부터 하나씩 추출·영향 분석·생성합니다. 순서는 `git rev-list`가 보장하고, 실패한 커밋은 완료로 기록하지 않으므로 다음 실행이 같은 커밋부터 재시도합니다. 처리 중 소스를 detached 로 체크아웃했다가 끝나면 원래 브랜치로 되돌립니다. 빌드 구성이 바뀌는 저장소는 `update.compdb_cmd`에 compile DB 재생성 명령을 둡니다. Gerrit 이벤트 훅이나 사내 CI 주기 작업에서 이 명령 하나를 부르면 되고, 수동 폴링은 `--watch --fetch`로 대신할 수 있습니다.
2. **관문.** 승인되지 않은 범위 검토 항목이 있으면 생성 전에(종료 코드 2), 생성 결과에 `needs-review` 페이지가 남으면 다음 커밋 전에(종료 코드 3) 멈춥니다. 자동 게시는 하지 않습니다.
3. **승인.** 사람이 검토를 마치면 `sdd accept <문서.md>`(원고 승인)과 `sdd accept --finding <장부 키>`(범위 항목 승인)로 장부에 기록합니다. `site.require_approval: true`와 함께 쓰면 승인 없는 문서는 게시되지 않습니다.
4. **게시.** 검증한 `export-site` 출력을 사내 운영 정책에 따른 배포 단계에서 웹 서버에 반영합니다. 생성기 자체는 서버 배포나 Git push를 수행하지 않습니다. CI로 연결할 때도 승인 장부와 실패 차단 조건을 유지합니다.

### 생성 모델 비교

문장 품질은 모델에 크게 좌우됩니다(4B 로컬 모델 실측: 표기·인용은 자동 검사로 보완했지만 설명 깊이는 한계). 사내 엔드포인트가 준비되면 같은 facts 로 모델만 바꿔 비교하세요. 출력 디렉터리를 분리한 설정 사본에서 `agent.kind: openai-compatible`과 `base_url`·`model`만 바꿔 `generate`를 실행하면 입력이 고정되어 문장 차이만 남습니다. 검사 통과율이 아니라, 표만으로 알 수 없는 것을 설명하는지와 확인되지 않은 것을 확인되지 않았다고 적는지를 봅니다.

## 4. 환경 없이 준비할 수 있는 것

사내 소스 없이 지금 할 수 있는 일입니다.

1. **진입점 목록 작성.** HAL3 인터페이스는 공개 규격이므로 `open`, `configure_streams`, `process_capture_request`, `flush`, `close`의 시그니처를 미리 적어 둘 수 있습니다. 실제 정의와의 대조만 나중에 합니다.
2. **문서 구성 결정.** 어떤 문서를 만들고 누구에게 보일지는 소스 없이 정할 수 있습니다. `config/sections.yaml`의 `group`과 `reader`가 그 결정을 담습니다.
3. **리허설.** `examples/mini-hal`이 그 목적의 최소 HAL입니다. 클래스 15개와 시나리오 6편으로 추출부터 사이트까지 전 과정이 돕니다. 사내 적용 전에 절차를 손에 익히는 용도로 쓸 수 있습니다.
4. **링크 형식 확인.** 사내 코드 열람 도구가 `blob/<sha>/<파일>#L<줄>` 형식을 쓰는지 확인해 두면, 인용이 코드로 연결되지 않는 문제를 미리 피할 수 있습니다.

## 5. 사내에서 확인해야 하는 것

libcamera에서 확인한 것이 사내에서도 같다고 가정하지 않습니다.

사내 HAL의 실제 소스 구성은 아직 확인하지 않았습니다. C++ 클래스 중심인 부분에는 클래스 표, 상속·필드 관계와 패키지 요약을 적용할 수 있습니다. 함수 포인터, 가상 호출, 큐와 콜백이 중심인 부분은 정적 추적이 끊기므로 해당 비중과 경계를 실제 소스에서 확인해야 합니다. 운영 환경에서 확인할 항목은 아래와 같습니다.

- **실제 빌드 시스템을 확인해야 합니다.** libcamera는 Meson으로 검증했으며 사내 HAL의 빌드 시스템은 아직 확인하지 않았습니다. libcamera에서도 Meson이 만든 DB를 그대로 넘겨 171개 TU가 전부 파싱에 실패했고, 경로를 절대 경로로 바꾸고 `-resource-dir`를 채운 뒤에야 통과했습니다. NDK/AOSP 등 다른 빌드에서도 실제 헤더와 인자를 대조해야 합니다.
- **게시 방식이 다릅니다.** GitHub Pages를 쓰지 않습니다. `export-site`의 출력은 정적 파일이므로 사내 웹 서버에 그대로 올릴 수 있지만, 경로와 접근 권한은 별도로 정해야 합니다.
- **모델이 다릅니다.** 문장 품질은 모델에 크게 좌우됩니다. libcamera 검증은 4B 모델로 수행했고, 그 결과 이름 표기와 인용을 자동 검사로 보완해야 했습니다.
- **반출 금지.** 사내 소스에서 파생된 facts, 문서, 프롬프트, 로그를 공개 저장소에 올리지 않습니다. 공개 저장소는 libcamera 검증 전용입니다.

## 근거와 검토 정보

- 설정 항목은 [설정 로더](../src/sdd/config.py)와 [libcamera 예제 설정](../examples/libcamera/sdd.yaml)에서 확인했습니다.
- 실행 순서와 확인 값은 [libcamera WSL2 실행 기록](libcamera-wsl-run.md)에서 실제로 수행한 결과입니다.
- 사내 전환 시 바뀌는 항목의 개요는 [가정용 검증 절차](libcamera-home-lab.md)의 마지막 절에 있습니다.

**이 문서의 절차는 사내 환경에서 실행되지 않았습니다.** 실행한 뒤 어긋난 부분을 이 문서에 반영해야 합니다.

다음 단계: [examples/mini-hal/sdd.yaml](../examples/mini-hal/sdd.yaml)을 열어 사내 설정에서 바꿀 항목이 어디에 있는지 확인합니다.
