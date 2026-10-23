# 3단계: 문서 갱신 시스템 만들기

**첫 실행을 마친 설정에 `update.compdb_cmd`를 추가하고 `sdd update --to origin/main`을 한 번 실행하세요.** 종료 코드 0이 나오면 시스템의 핵심이 동작하는 것입니다. 그다음 예약 실행과 게시를 붙입니다. 전체 구축에 반나절 정도 걸립니다.

```
1단계 준비물 → 2단계 첫 실행 → [3단계 갱신 시스템] → 4단계 사람 검토
```

## 시스템이 하는 일

```
새 커밋 (HAL 저장소)
   │  sdd update: 오래된 커밋부터 하나씩
   ├─ 1. 체크아웃 → compile DB 재생성 (update.compdb_cmd) → 사실 추출
   ├─ 2. 이전 커밋과 비교 → 다시 만들 문서 + 범위 검토 항목
   │        ├─ 주석·공백·#include 만 바뀜, 빌드 밖 파일 → 자동 분류 (관문 통과)
   │        ├─ LLM 판정 (선택)              → "범위 밖"만 통과 (pass_gate: true 일 때)
   │        └─ 남은 항목                    → 멈춤, 종료 코드 2 (사람 판단)
   ├─ 3. 영향 받은 문서만 다시 생성, 나머지는 인용을 재검증해 이월
   └─ 4. needs-review 원고가 있으면 멈춤, 종료 코드 3 (사람 검토)
   ▼
export-site → verify-site → 게시 (사내 웹 서버 / 문서 저장소)
```

실패한 커밋은 완료로 기록하지 않습니다. 같은 명령을 다시 실행하면 그 커밋부터 재시도합니다.

## A. 커밋마다 갱신

30분 정도 걸립니다.

1. `sdd.yaml`에 compile DB 재생성 명령을 추가합니다. 이 명령은 소스 루트에서 실행되고, ndk-build를 쓰면 실행 뒤 자동으로 정규화합니다.

   ```yaml
   update:
     compdb_cmd: ["ndk-build", "compile_commands.json"]
   ```

   `jni/`의 부모(`ndk_build.project_dir`)가 소스 루트와 다르면 `["ndk-build", "-C", "<project_dir>", "compile_commands.json"]`로 디렉터리를 명시합니다.

2. 분석 전용 체크아웃의 `.git/info/exclude`에 `compile_commands.json`을 한 줄 추가합니다. ndk-build가 만든 이 파일이 추적되지 않는 파일로 남으면 `sdd update`가 "소스 저장소에 커밋되지 않은 변경이 있습니다"라며 시작하지 않습니다. 이 파일은 로컬에만 적용되어 HAL 저장소에 커밋되지 않습니다.

3. 실행합니다.

   ```bash
   uv run sdd --config ../hal-sdd-project/sdd.yaml update --to origin/main --fetch
   ```

4. 종료 코드를 확인합니다. 2·3이면 [4단계: 사람 검토](04-review.md)로 처리한 뒤 같은 명령을 다시 실행합니다.

## B. 범위 판단을 줄이기

선택 사항입니다. 15분 정도 걸립니다.

바뀐 파일의 클래스를 다루는 문서가 없으면 갱신이 멈춥니다(종료 코드 2). 두 가지로 줄입니다.

1. **구성 요소 색인**: [2단계](02-first-run.md#3-무엇을-문서화할지-정하기)의 색인을 두면 빌드한 코드는 모두 어떤 문서가 다룹니다. 가장 효과가 큽니다.
2. **LLM 판정**: 남은 항목을 모델이 먼저 판정합니다.

   ```yaml
   review:
     coverage_triage:
       enabled: true
       pass_gate: false     # true 면 "범위 밖" 판정이 관문을 통과시킵니다
   ```

   `pass_gate`를 켤지는 운영 정책입니다. 사람 승인이 필요한 운영이나 외부 기여를 받는 저장소에서는 끕니다. 판정이 어떻게 기록되고 무엇이 위험한지는 [범위 검사](../concepts/coverage.md#판단을-줄이는-두-단계)에 있습니다.

## C. 예약 갱신과 게시

1~2시간 정도 걸립니다.

두 방식 중 하나를 고릅니다.

| 방식 | 언제 | 하는 일 |
|---|---|---|
| CI·cron에서 `sdd update` | 게시는 기존 배포 절차로 따로 합니다. | 갱신만 합니다. 성공하면 `export-site`·`verify-site` 뒤 사이트 디렉터리를 배포합니다. |
| `sdd automate` | 갱신부터 게시·URL 확인까지 한 작업으로 돌립니다. | 갱신 → Hermes 재검토(선택) → 사이트 검증 → 문서 저장소 커밋·push → 배포 → 실제 URL 해시 확인. 실패하면 그 단계부터 재개합니다. |

`sdd automate`를 쓰는 순서입니다.

1. `sdd.yaml`에 `automation`을 추가합니다. 키는 [automation 참조](../reference/config.md#automation)에 있습니다.

   ```yaml
   automation:
     to: origin/main
     fetch: true
     schedule: {time: "07:30", timezone: Asia/Seoul, command: [/opt/sdd/bin/sdd, --config, "{config}", automate]}
     publish:
       repo: ../hal-docs-publisher
       directory: docs
       remote: origin
       branch: main
       verify_command: [/opt/sdd/bin/sdd, verify-publication, --url, "https://docs.internal/hal/"]
   ```

2. 한 번 직접 실행해 끝까지 통과하는지 봅니다.

   ```bash
   uv run sdd --config ../hal-sdd-project/sdd.yaml automate
   ```

3. 예약 항목을 출력해 crontab에 등록합니다. 자동으로 설치하지 않습니다. 시간을 바꾸면 다시 출력해 교체합니다.

   ```bash
   uv run sdd --config ../hal-sdd-project/sdd.yaml automate --cron
   ```

실패 후 재개 규칙, Hermes 재검토(`automation.hermes`)와 누락 보완(`automation.idle_review`)이 바꾸는 범위는 [sdd automate 동작 방식](../concepts/automation.md)에 있습니다. Gerrit change마다 문서를 만들려면 [`ci/gerrit-hook.sh`](../../ci/gerrit-hook.sh)를 씁니다.

## 지켜야 할 것

1. **같은 설정·출력으로 동시에 두 번 실행하지 않습니다.** `sdd automate`는 OS 잠금으로 막지만, CI에서 `sdd update`를 직접 부르면 스케줄러에서 직렬화해야 합니다.
2. **상태 파일을 실행 사이에 보존합니다.** 목록은 [build에 생기는 파일](../reference/cli.md#build에-생기는-파일)의 굵은 항목입니다.
3. **전체 재생성은 기준이 바뀔 때만 합니다.** 빌드 구성(`-D`, 빌드 대상), 문서 정의(`sections.yaml`), 집필 규칙(`style/`)이 바뀌면 그 시점의 커밋에서 다시 기준을 잡습니다. 분석 체크아웃을 `update-state.json`의 마지막 처리 커밋(`last_done`)으로 체크아웃한 뒤 **세 명령을 모두** 실행합니다. 중간에 멈췄으면 처음부터 다시 실행합니다.

   ```bash
   uv run sdd --config ../hal-sdd-project/sdd.yaml compdb --regenerate
   ```

   ```bash
   uv run sdd --config ../hal-sdd-project/sdd.yaml extract
   ```

   ```bash
   uv run sdd --config ../hal-sdd-project/sdd.yaml generate
   ```

   첫 명령이 바뀐 빌드 구성으로 compile DB를 다시 만듭니다. 이것을 빼면 옛 DB로 추출합니다. `generate`를 빼면 새 커밋이 없을 때 `sdd update`가 아무것도 다시 만들지 않으므로 문서가 옛 facts에 남습니다. 그다음 `sdd update`를 이어서 실행합니다.

다음 단계: 갱신이 멈췄을 때 할 일은 [4단계: 사람 검토](04-review.md)에 있습니다.
