# 원하는 시간에 문서를 갱신하고 게시하기

**사내 프로젝트 설정에 `automation`을 추가하고 `sdd automate`를 한 번 실행하여 검증하세요.** 실행기는 생성기 저장소에서 공급하고 소스·설명 설정·상태·Hermes 기록·출력은 사내에 보관합니다. 사내 HAL 운영 검증을 완료한 기능이라는 뜻은 아닙니다.

## 준비

[문서 수명주기 설정](document-lifecycle.md)으로 분량·중복·Feature 범위 관문을 켭니다. 게시 전 검사 실패는 `build` 단계에 기록되며 원격 문서 저장소를 변경하지 않습니다. 실행 중인 게시의 수명주기 설정을 바꾸면 기존 작업을 조용히 재사용하지 않고 중단합니다.

1. 분석 전용 HAL 체크아웃과 실제 제품의 compile DB·생성 헤더를 준비합니다.
2. 별도 설정 디렉터리에 `sdd.yaml`, `sections.yaml`, `scenarios.yaml`을 둡니다. 기준 커밋에서 `extract`와 `generate`를 실행합니다.
3. 게시 브랜치를 체크아웃한 전용 문서 저장소를 준비합니다. 기존 수정이나 미게시 커밋이 있으면 실행기가 멈춥니다.
4. Hermes를 설치하고 사내 QWEN provider를 구성합니다. 모델 선택·인증·외부 fallback 정책은 Hermes 실행 환경에서 관리합니다.
5. 배포 완료와 실제 게시 URL의 manifest·산출물 해시를 검사하는 명령을 준비합니다. Git push 성공이나 HTTP 200만으로 성공 처리하지 않습니다.

## 설정

다음을 `sdd.yaml`에 추가합니다. 경로는 설정 파일 기준이며, 명령은 셸 문자열이 아닌 인자 목록입니다. 환경 변수나 `~`를 경로에서 자동 확장하지 않습니다.

```yaml
automation:
  to: origin/main
  fetch: true
  schedule:
    time: "21:00"
    timezone: Asia/Seoul
    command: [/opt/sdd/bin/sdd, --config, "{config}", automate]
  hermes:
    enabled: true
    command: [hermes, --ignore-rules, --toolsets, todo, --reasoning, none, -z, "{prompt}"]
    timeout_sec: 600
    max_input_chars: 24000
  publish:
    repo: ../hal-docs-publisher
    directory: docs
    remote: origin
    branch: main
    # Git push 자체가 배포를 시작하는 환경에서는 생략합니다.
    deploy_command: [/opt/company/bin/deploy-hal-docs]
    verify_command: [/opt/sdd/bin/sdd, verify-publication, --url, "https://docs.internal/hal/", --timeout, "600"]
    timeout_sec: 900
update:
  compdb_cmd: [/opt/company/bin/prepare-hal-analysis]
site:
  # 검토용 자동 게시에서는 false, 사람 승인 필수 게시에서는 true로 설정합니다.
  require_approval: false
  mermaid_dir: assets/mermaid
```

Hermes CLI 옵션은 로컬 v0.21.3을 기준으로 합니다. 사내 버전이 다르면 동일한 입출력 계약을 제공하는 wrapper로 `command`를 교체하세요. `{prompt}`는 한 인자로 전달하고 stdout에는 JSON 하나만 반환합니다. 인증 토큰은 명령 인자에 넣지 않습니다.

기본 도구 집합은 `todo`로 제한하여 파일 수정·터미널·네트워크 도구를 제외합니다. 제공한 발췌를 읽고 JSON 제안만 반환하도록 요청하며, 실제 설정 반영은 생성기가 수행합니다. Hermes의 `none` 도구 집합은 이 버전에서 유효하지 않습니다.

배포·확인 명령은 문서 저장소 루트에서 실행하며 다음 환경 변수를 받습니다.

| 변수 | 의미 |
|---|---|
| `SDD_SOURCE_COMMIT` | 이번 문서의 HAL 커밋입니다. |
| `SDD_DOCS_COMMIT` | push한 문서 저장소 커밋입니다. |
| `SDD_SITE_DIR` | 검증한 로컬 사이트의 절대 경로입니다. |
| `SDD_BUILD_ID` | 실제 게시되어야 하는 manifest의 build ID입니다. |

확인 명령은 제한 시간 안에서 실제 배포 완료를 기다리고 기대한 ID·해시와 일치할 때만 종료 코드 0을 반환해야 합니다. 배포 명령은 같은 커밋으로 재호출해도 안전해야 합니다. 특정 게시 호스트는 공통 실행기에 고정하지 않습니다.

내장 `verify-publication`은 로컬 manifest와 실제 URL의 manifest·모든 산출물 해시를 대조합니다. 사내 인증 방식이 별도로 필요하면 같은 검사 계약을 수행하는 사내 명령으로 교체합니다.

## 원하는 시간으로 변경하기

```bash
/opt/sdd/bin/sdd --config /srv/hal-project/sdd.yaml automate
/opt/sdd/bin/sdd --config /srv/hal-project/sdd.yaml automate --cron
```

두 번째 명령은 다음 사용자 crontab 항목을 출력하며 자동 설치하지 않습니다.

```cron
CRON_TZ=Asia/Seoul
0 21 * * * /opt/sdd/bin/sdd --config /srv/hal-project/sdd.yaml automate
```

`time: "07:35"`로 바꾸고 출력한 항목으로 기존 예약을 교체하면 매일 오전 7시 35분에 실행합니다. **설정 파일만 수정하면 이미 설치한 crontab이 자동으로 바뀌지는 않습니다.** 같은 작업을 중복 등록하지 않습니다.

이 출력은 `CRON_TZ`를 지원하는 Cronie 등의 cron용입니다. 지원하지 않는 cron에서는 호스트 시간대를 맞추거나 시간대를 지원하는 CI 스케줄러를 사용합니다. Windows 작업 스케줄러에서도 동일한 실행 명령을 등록할 수 있으나 Windows 예약 작업을 자동 설치하지 않습니다. 실행 계정의 PATH·Git 자격 증명·Hermes 설정을 준비합니다.

## Hermes의 수정 범위

Hermes는 소스 해시가 바뀐 `design_topics`의 기존 `statements`를 검토합니다. 주제별로 질문·기존 설명·변경 전후 발췌를 전달합니다. 입력 한도를 넘으면 잘라 보내지 않고 실패합니다. 응답에 검토 이유와 근거를 연결한 설명이 있어야 합니다.

기존 필수 질문·근거 검사를 통과한 제안만 `sections.yaml`에 원자적으로 반영합니다. 현재 발췌의 해시는 실행기가 계산합니다. YAML 주석·표현 형식은 재직렬화될 수 있습니다. 수정된 설정을 사내 버전 관리에 보관하세요.

검토를 시작할 때 원본 설정을 보관하고, Hermes 응답을 기다리는 동안 설정이 바뀌었으면 제안을 반영하지 않습니다. 사용자의 최신 편집을 유지한 상태에서 다시 실행하세요.

앵커 누락·범위 누락·답변 부족은 자동으로 완화하지 않습니다. 커밋 갱신에서는 기존 질문·선택자를 유지합니다. 최초 문서 범위 구성은 별도 작업이며, 기존 카테고리 안의 누락 보완은 아래 옵션으로 켭니다. facts 기반 문서는 LLM 없이 생성하고 일반 LLM 서술 섹션은 기존 `agent` 설정을 사용합니다.

원본 설정·프롬프트·원응답은 `build/hermes/<HAL-SHA>/`에 보관합니다. 자동 검사와 Hermes의 재검토는 사람의 승인이 아니며 `sdd accept`를 호출하지 않습니다. `site.require_approval: true`이면 기존 승인 관문을 유지합니다. 설명의 의미 정확성은 별도 검증이 필요합니다.

## 커밋이 없는 날의 누락 보완

`automation`에 다음 옵션을 추가하면 **실행 시작 시 미처리 커밋이 없는 날에만** 누락을 점검합니다. 기본값은 비활성화이며 `hermes.enabled: true`가 필요합니다. 실행 시간은 기존 `schedule`을 그대로 사용합니다.

```yaml
automation:
  idle_review:
    enabled: true
    # 생략하면 기존 prose/per-scenario 섹션을 순서대로 점검합니다.
    sections: [camera-model, scenarios]
    # 생략하면 선택한 섹션의 watch glob을 사용합니다.
    files: [src/libcamera/camera.cpp, src/libcamera/request.cpp]
    source_chars: 5000
    revision: 1
```

위 ID와 경로는 libcamera 예시입니다. 사내 HAL에서는 실제 섹션 ID와 파일 glob으로 바꿉니다. 한 번에 소스 창 하나를 읽고 최대 한 항목을 보완합니다. 소스를 파일·문자 위치 순서로 나누어 점검하므로 전체 누락을 한 번에 찾아내는 기능은 아닙니다. `source_chars`는 500~12000이며, 입력 전체가 Hermes 한도를 넘으면 보류합니다.

1. Hermes에 기존 질문·설명, 시나리오 목록과 고정한 커밋의 소스 발췌를 전달합니다.
2. 기존 prose 섹션에는 근거가 연결된 질문·설명을, 기존 per-scenario 섹션에는 실제 진입점을 추가할 수 있습니다. 새 최상위 카테고리는 만들지 않습니다.
3. 별도 작업 디렉터리에서 근거 해시·원고·사이트를 검증합니다. 새 시나리오는 compile DB로 다시 추출하며 진입점 누락이나 노드 한도 초과를 통과시키지 않습니다.
4. 검증을 통과하면 설정·facts·원고를 반영하고 기존 게시 단계를 수행합니다. 변경할 내용이 없으면 불필요한 게시 커밋을 만들지 않습니다.

부족한 근거, 잘못된 JSON, 승인 관문 실패는 `deferred`로 기록하며 원본을 유지합니다. 자동 검사는 설명의 의미 정확성이나 사람 승인을 보증하지 않습니다. `site.require_approval: true`일 때 승인되지 않은 제안은 작업 디렉터리에 남으며 자동 게시되지 않습니다. 운영자는 감사 기록을 검토하고 기존 승인 절차로 별도 반영해야 합니다.

같은 소스 창은 동일 커밋·revision에서 다시 점검하지 않습니다. 제안 ID도 중복 반영하지 않습니다. 표현만 다른 의미상 중복을 완전히 검출하지는 못합니다. 보류 원인을 고친 뒤 `revision`을 올리면 새 점검을 시작합니다. 설정 범위를 변경하거나 revision을 올리기 전에 미완료 게시를 먼저 재개하세요.

예약 없이 **로컬 누락 점검만 한 번** 실행하려면 다음을 사용합니다. 이 명령도 검증된 제안을 설정·원고에 반영하지만 Git 게시를 수행하지 않습니다. `idle_review.enabled` 없이도 명시적으로 실행할 수 있습니다.

```bash
sdd --config /srv/hal-project/sdd.yaml improve
```

`build/idle-review-state.json`에 점검 위치·결과·반영 중인 파일 해시를, `build/idle-review/<실행 ID>/`에 프롬프트·응답·검증 산출물을 보관합니다. 반영 중 종료되면 같은 명령이 같은 제안을 재개합니다. 실행 도중 사용자가 수정한 원본은 덮어쓰지 않습니다. 상태와 작업 디렉터리는 함께 보존하고 사내 입력으로 만든 기록은 공개 저장소에 올리지 않습니다.

## 실패 후 재개

`sdd automate`를 다시 실행합니다. 시작 시 고정한 HAL SHA의 게시가 끝나기 전에는 더 새로운 커밋으로 넘어가지 않습니다.

| 실패한 단계 | 다음 실행의 동작 |
|---|---|
| 추출·생성·검토 | `update-state.json`의 기준에서 재개하며 기존 관문을 유지합니다. |
| 사이트 검증 | 기존 게시 작업본을 유지하며 빌드를 재시도합니다. |
| 커밋·push | 검증한 산출물과 문서 커밋을 재사용합니다. |
| 배포·URL 확인 | 해당 단계만 재시도하며 마지막 게시 성공 SHA는 전진하지 않습니다. |
| 변경 없음 | 빈 커밋을 만들지 않으며 마지막 확인 결과와 산출물이 같으면 배포도 생략합니다. |

`build/automation-state.json`은 처리 상태와 별도로 게시 단계·마지막 확인 성공을 기록합니다. `build/automation-site`, facts, 원고, 수정된 sections 설정, 승인 장부와 두 상태 파일을 실행 사이에 보존하세요. 미완료 작업의 게시 설정을 바꾸면 중단하며 시간 설정만 변경하는 것은 허용합니다.

`publish.remote`는 등록된 Git remote 이름이며, 실제 fetch·push URL도 게시 대상 식별에 포함합니다. 미완료 게시 중 원격 주소가 바뀌면 재개를 중단합니다. 게시 완료 후 배포·확인 설정을 바꾼 경우에는 산출물이 같더라도 새 설정으로 배포와 확인을 수행합니다. 이전 버전에서 진행 중인 게시가 있으면 해당 버전으로 마무리한 뒤 업그레이드하세요. 이전 성공 기록에 설정 식별자가 없으면 다음 실행에서 한 번 더 배포를 확인합니다.

같은 설정의 중복 실행은 OS 잠금으로 거절합니다. 다른 설정이 같은 소스·출력·문서 작업본을 공유하는 경우 운영 스케줄러에서도 공통 잠금을 구성해야 합니다. `sdd update`를 같은 작업본에서 동시에 직접 실행하지 않습니다. 프로세스가 종료되면 잠금은 풀리므로 lock 파일을 삭제하지 않습니다.

다음 단계: [사내 적용 절차](inhouse-adoption.md)의 실제 제품 입력을 준비하세요.
