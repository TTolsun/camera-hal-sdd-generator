---
name: camera-hal-sdd
description: 사내 Camera HAL(NDK-build, legacy HAL3) 소스에서 camera-hal-sdd-generator의 sdd CLI로 설계 문서(SDD)를 추출·생성·검증하고 새 커밋에 맞춰 증분 갱신할 때 사용한다. "SDD 만들어 줘", "설계 문서 갱신", "sdd extract/generate/update 실행", "추출 오류 해결" 같은 요청에 사용한다. 문서 내용을 직접 쓰거나 사람 승인을 대신하는 용도가 아니다.
metadata:
  version: "1"
  repository: camera-hal-sdd-generator
---

# Camera HAL SDD 생성

이 스킬은 `sdd` CLI를 실행하고, 출력에서 확인할 값을 읽고, 멈춰야 할 때 멈추는 절차다. 문서의 문장은 생성기가 설정된 모델로 만든다. 너는 명령을 실행하고 결과를 판단하고 보고한다.

## 먼저 알아 둘 것

- 생성기 저장소 루트에서 명령을 실행한다. 모든 명령에 `--config <사내설정>/sdd.yaml`을 붙인다. 아래에서는 이 경로를 `$CFG`로 적는다.
- 너(에이전트)와 생성기의 문장 모델은 다르다. 생성기의 모델은 `sdd.yaml`의 `agent` 설정이 정한다. 네가 이 저장소에서 작업한다고 생성기가 너를 모델로 쓰지 않는다.
- 상세 절차와 오류 표는 `docs/inhouse-ndk-hal3.md`에 있다. 이 스킬의 표에 없는 메시지를 만나면 그 문서의 "6. 문제 해결"을 읽는다.

## 절대 하지 않는 것

1. 생성된 Markdown(`sdd/`)이나 HTML(사이트 출력)을 직접 고치지 않는다. 고쳐야 하면 설정(`config/*.yaml`)이나 생성기 코드를 고치고 다시 생성한다.
2. `sdd accept`를 사람 대신 실행하지 않는다. 사람이 검토를 마쳤다고 대화에서 직접 말한 문서만 기록한다.
3. 근거 해시(`evidence`의 SHA-256)만 바꿔서 검사를 통과시키지 않는다. 근거가 바뀌면 연결된 설명을 소스와 다시 대조한다.
4. 검사를 끄거나 완화해서 성공으로 만들지 않는다. 예: `site.require_approval: false`, `review.require_citations: false`, 시나리오 삭제.
5. 사내 소스, facts, 원고, 프롬프트, 로그를 사내 밖(공개 저장소, 외부 서비스)으로 보내지 않는다.

## 요청별 절차 선택

| 요청 | 절차 |
|---|---|
| 처음 문서를 만든다 | A |
| 새 커밋을 문서에 반영한다 | B |
| 명령이 실패했다 | C |
| 진입점(시나리오)을 추가하거나 고친다 | D |

## A. 처음 생성

각 단계의 확인 값이 맞지 않으면 다음 단계로 가지 않고 C로 간다.

1. 환경 점검

   ```bash
   uv run sdd --config $CFG doctor
   ```

   확인: 종료 코드 0, compile DB 경고 없음.

2. 사실 추출

   ```bash
   uv run sdd --config $CFG extract
   ```

   확인: `[comments] ... 파싱 오류 0 개`, `[callgraph] ... 진입점 못 찾음 0 개`. 클래스 수가 0이거나 지나치게 적으면 멈추고 보고한다.

3. 문서 생성

   ```bash
   uv run sdd --config $CFG generate
   ```

   확인: `status: needs-review` 페이지 목록을 기록한다. 이 페이지는 사람 검토 대상이다.

4. 사이트 생성과 검증

   ```bash
   uv run sdd --config $CFG export-site
   ```

   ```bash
   uv run sdd --config $CFG verify-site
   ```

   확인: `broken_links: 0`. `site.require_approval: true`에서 미승인 문서 때문에 `export-site`가 막히는 것은 정상이다. 승인을 대신 기록하지 말고 보고한다.

## B. 증분 갱신

```bash
uv run sdd --config $CFG update --to origin/main
```

종료 코드로 다음 행동을 정한다.

| 종료 코드 | 뜻 | 너의 행동 |
|---|---|---|
| 0 | 새 커밋을 모두 처리했다 | A의 4단계(사이트 생성과 검증)를 실행한다. |
| 1 | 한 커밋의 처리가 실패했다 | 로그의 원인으로 C를 수행한다. 해결 후 같은 명령을 다시 실행하면 같은 커밋부터 재시도한다. |
| 2 | 승인되지 않은 범위 검토 항목이 있다 | `build/impact-review.md`를 요약해 보고하고 멈춘다. `sdd accept --finding`은 사람이 결정한다. |
| 3 | `needs-review` 페이지가 있다 | 페이지 목록과 사유를 보고하고 멈춘다. `sdd accept`는 사람이 결정한다. |

"소스 저장소에 커밋되지 않은 변경이 있습니다"로 시작하지 않으면, 분석용 HAL 체크아웃의 `git status`를 보고한다. ndk-build가 만든 `compile_commands.json`이 원인이면 그 체크아웃의 `.git/info/exclude`에 한 줄 추가한다. 다른 파일이 원인이면 지우지 말고 보고한다.

## C. 오류 대응

| 메시지에 포함된 문구 | 조치 |
|---|---|
| `Clang 파싱 오류` | 생성 헤더가 있는지, ndk-build를 제품 빌드와 같은 `ndk_build.args`로 실행했는지 확인한다. 추측한 `-I`를 설정에 넣어 통과시키지 않는다. |
| `컴파일러가 clang 이 아니라 실행하지 않습니다` | 사람에게 NDK clang 경로를 받아 `source.ndk_build.clang`에 적는다. 경로를 추측하지 않는다. |
| `clang 내장 헤더 위치를 확인하지 못했습니다` | 이 머신의 NDK clang 경로를 찾아 `source.ndk_build.clang`에 적는다. 찾지 못하면 보고한다. |
| `진입 함수를 정하지 못했습니다` | D를 수행한다. |
| `응답 파일(@...)` | 보고한다. 빌드 설정 변경이 필요하다. |
| 그 밖의 메시지 | `docs/inhouse-ndk-hal3.md`의 "6. 문제 해결"을 읽는다. 없으면 메시지 원문과 실행한 명령을 보고한다. |

같은 오류로 두 번 실패하면 더 시도하지 않고 보고한다.

## D. 시나리오 진입점

`config/scenarios.yaml`의 `from`에 실제 정의의 시그니처를 적는다.

1. 소스에서 정의를 찾는다. 헤더 선언이 아니라 `.cpp`의 정의를 본다.
2. `네임스페이스::클래스::함수(인자 타입, ...)` 형태로 적는다. 인자 이름은 빼고, 타입은 소스에 적힌 대로 쓴다. `struct` 키워드는 있어도 없어도 된다.
3. 대조한 위치를 주석으로 남긴다. 예: `# 정의: device/CameraDevice.cpp:120`
4. `extract`를 다시 실행해 `진입점 못 찾음 0 개`를 확인한다.

"같은 이름의 정의가 N개라 고를 수 없습니다" 메시지는 괄호 안에 후보를 보여 준다. 그중 의도한 정의를 골라 클래스와 인자를 붙인다. 어느 것이 의도인지 모르면 후보 목록을 보고하고 묻는다.

`process_capture_result`, `notify` 같은 framework 콜백이 "함수 포인터, 정적 추적 불가"로 표시되는 것은 정상이다. HAL에서 framework로 돌아가는 경계다.

## 보고 형식

작업을 끝내거나 멈출 때 아래 순서로 보고한다.

```text
결과: <완료 | 멈춤 | 실패>
설정: <$CFG 경로>, 소스 SHA: <facts.json meta.source_commit>
실행한 명령과 종료 코드:
  - <명령> → <코드>
확인 값: 파싱 오류 <n>, 진입점 못 찾음 <n>, needs-review <페이지 목록>, broken_links <n>
사람이 결정할 것: <승인 대상, 받아야 할 경로 등. 없으면 "없음">
검증하지 못한 것: <없으면 "없음">
```

자동 검사 통과(`ok`, `mapped`, `documented`)를 "검토 완료"나 "승인"이라고 쓰지 않는다.
