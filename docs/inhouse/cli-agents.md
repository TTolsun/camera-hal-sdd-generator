# 문서 생성 CLI 선택

**사내에서 승인하고 사용자가 선택한 CLI를 `agent.runner`로 지정하세요.** Hermes, OpenCode, Claude Code, Codex를 같은 설정 방식으로 선택합니다. 생성기는 해당 CLI를 독립적으로 실행하며 다른 CLI나 모델 API로 자동 전환하지 않습니다. 공개 프로필과 사내 템플릿에 적힌 Codex/Terra High는 저장소의 기본 예시이며 사내 필수 의존성이 아닙니다. 기존 사내 선택을 유지하고 신규 적용에서 선택이 없으면 모델 호출 전에 확인합니다.

| 사용할 CLI | `agent.runner` | 모델·제공자·추론 설정 |
|---|---|---|
| Hermes | `hermes` | 승인된 Hermes 설정 또는 실행별 `model`·`args`를 사용합니다. |
| OpenCode | `opencode` | 승인된 OpenCode 설정 또는 해당 CLI의 `provider/model` ID·인자를 사용합니다. |
| Claude Code | `claude` | 승인된 Claude Code 설정 또는 해당 CLI의 모델 ID·인자를 사용합니다. |
| Codex | `codex` | 격리 실행에서 사용자 설정을 읽지 않으므로 승인된 모델·추론 강도를 `model`·`args`에 명시합니다. |

다음은 Hermes를 선택한 **로컬 덮어쓰기** 예시입니다. [동봉 예시](../../examples/inhouse-template/sdd.cli.local.example.yaml)를 `sdd.yaml` 옆의 `sdd.local.yaml`로 복사하세요. 기존 파일이 있으면 다른 설정을 보존하고 `agent`만 병합합니다. 다른 CLI를 선택하면 `runner`와 해당 CLI의 설정을 함께 바꿉니다.

```yaml
agent:
  kind: cli
  runner: hermes
  command: []
  model: ""
  args: []
  timeout_sec: 600
  max_input_chars: 30000
```

## 실행기와 모델 변경

1. 사용할 CLI를 설치하고 사내에서 허용한 모델·제공자·인증을 해당 CLI에 설정합니다. CLI가 지원하면 Ollama를 모델 제공 서버로 사용할 수 있으며 생성기 → 선택한 CLI → 승인된 모델 순서로 호출합니다. Qwen이나 외부 제공자를 필수로 가정하지 않습니다.
2. `sdd.local.yaml`에서 `runner`·`command`·`model`·`args`를 함께 지정합니다. 실행 전에 기본 파일과 로컬 덮어쓰기를 합친 최종 값을 확인합니다. 파일명이 `sdd.review.yaml`이면 로컬 파일은 `sdd.review.local.yaml`입니다. 앱·CLI의 전역 기본값이나 현재 채팅 모델은 변경하지 않습니다.
3. `uv run sdd --config <CFG> doctor`를 실행합니다. 실행 파일을 확인하며, 기본 실행기는 버전도 확인합니다. 인증·네트워크·모델 접근은 해당 CLI에서 따로 확인합니다.
4. 공개 입력 또는 사내에서 허용된 입력으로 `generate`를 실행하고 원응답·검사 결과를 확인합니다. CLI가 없거나 실패하면 설치·인증·모델 설정을 고친 뒤 같은 실행기로 다시 실행합니다.

실행별 모델을 지정하려면 해당 CLI가 받는 모델 ID를 `model`에 적습니다. **로컬 덮어쓰기에서 키를 생략하면 기본 파일의 값이 남습니다.** `model: ""`로 명시하면 CLI 기본 모델을 사용하고, `args: []`는 기존 전용 인자를, `command: []`는 기존 실행 경로를 제거합니다. `model: null`은 사용하지 않습니다. 제공자나 추론 설정 등은 선택한 CLI의 `args` 목록에 넣으며 목록 전체가 교체됩니다. 특정 CLI·모델의 인자를 다른 실행기로 그대로 넘기지 않습니다.

빈 모델은 실행기의 기본 선택에 맡긴다는 뜻이며, 모든 CLI가 사용자 설정 파일을 읽는다는 뜻은 아닙니다. 특히 Codex는 아래의 격리 실행 규칙에 따라 사용자 설정을 읽지 않으므로 승인된 모델과 추론 강도를 명시하세요.

```yaml
agent:
  kind: cli
  runner: hermes
  command: []
  model: qwen3.5:9b-ctx64k
  args: [--provider, custom, --reasoning, high]
```

OpenCode에서는 `runner: opencode`와 해당 CLI의 `provider/model` ID를, Claude Code에서는 `runner: claude`와 해당 CLI가 지원하는 모델 ID를 사용합니다. 모델 제공자와 지원 모델은 CLI별로 다르므로 모든 CLI가 모든 모델을 지원한다고 가정하지 않습니다. 위 Qwen 설정은 공개 시험 예제이며 사내 기본 모델을 지정하지 않습니다.

`qwen3.5:9b-ctx64k`는 공개 시험 환경에 준비한 모델 프리셋 이름입니다. 해당 환경에서는 같은 9B 가중치에 `num_ctx=65536`을 설정했습니다. 다른 환경에서는 준비한 모델 ID와 컨텍스트 설정을 사용하세요. 생성기의 `agent.num_ctx`는 Hermes에 전달되지 않으며, `--reasoning high`는 컨텍스트 크기와 별도로 지정하는 추론 강도입니다.

공개 libcamera의 기본 Codex/Terra High 프로필은 [예제 설정](../../examples/libcamera/sdd.yaml)에 저장합니다. 사용자가 공개 환경에서 Hermes/Qwen 시험을 별도로 선택하면 위 모델과 `high`를 사용합니다. 기존 HTTP·CLI 시험 기록의 모델이나 추론 설정은 바꾸지 않습니다.

## 생성·번역과 검토 설정

사내 생성·번역에는 선택한 CLI를 사용하며, 별도 근거 검토에도 조직에서 승인한 실행기·모델을 명시합니다. 검토를 분리할 때는 별도 설정과 실행으로 관리하고 생성 프로필을 덮어쓰지 않습니다. 한 CLI가 다른 CLI를 호출하는 구성으로 해석하지 않습니다. 같은 모델의 검토와 독립 평가, 사람 승인을 구분합니다.

이 공개 프로젝트의 LLM 근거 대조에는 프로젝트 지침에 따라 별도 설정의 독립 Codex CLI/Terra High를 사용합니다. 아래는 그 검토 프로필이며 사내 전체에 강제하는 기본값이 아닙니다. 사내에서 Codex를 승인하지 않았다면 자동으로 호출하지 않고 승인된 검토 설정을 사용합니다. 과거 실행 기록은 당시 모델·인자를 그대로 보존합니다.

```yaml
agent:
  kind: cli
  runner: codex
  command: []
  model: gpt-6.1-terra
  args: [-c, 'model_reasoning_effort="high"']
```

계약 대조에는 이 `agent` 블록만 담은 검토 설정 파일을 `paths.consistency_profile`에 지정할 수 있습니다. 주 설정으로 `audit-consistency`를 실행하면 소스, 원고, 검토 대상과 예산은 주 설정에서 읽고 CLI 설정만 검토 프로필에서 읽습니다. 실패하면 해당 실행 기록의 검토 상태를 확인합니다. [첫 실행 절차](02-first-run.md)

사내에서는 자체 `sdd.yaml`을 사용하거나 `sdd.local.yaml`로 모델·제공자·추론 강도를 교체할 수 있습니다. 예를 들어 다음 값은 공개 예제의 `model`과 `args`를 대체합니다. `args`는 목록 전체가 교체되므로 사용할 실행기의 인자를 모두 적으세요.

```yaml
agent:
  kind: cli
  runner: hermes
  command: []
  model: approved-internal-model
  args: [--provider, approved-provider, --reasoning, high]
```

다른 CLI로 바꿀 때도 해당 CLI의 모델 ID와 인자를 함께 지정합니다. 추가 인자가 없으면 `args: []`로 이전 실행기의 인자를 지웁니다. 공통 생성기에는 공개 Qwen 모델을 하드코딩하지 않습니다.

CLI 실행 파일이나 사내 실행 래퍼를 지정해야 한다면 `command: ["/approved/path/hermes"]`처럼 실행 접두사를 인자 목록으로 적습니다. 생성기가 각 CLI의 비대화형 옵션을 이어 붙입니다. 셸 명령 문자열을 넣지 않으며 인증 토큰은 `args`나 `command`에 넣지 않습니다. 각 CLI에서 승인된 인증 수단으로 관리합니다.

## Codex CLI의 Terra High

저장소의 루트 설정·공개 예제·사내 기본 템플릿에 명시한 프로필은 다음과 같습니다. 사내에서 다른 실행기를 선택하면 앞의 로컬 덮어쓰기를 적용합니다. 과거 실행 기록은 당시 설정을 유지합니다.

```yaml
agent:
  kind: cli
  runner: codex
  command: []
  model: gpt-6.1-terra
  args: [-c, 'model_reasoning_effort="high"']
```

생성기 → Codex CLI → 선택한 모델 순서로 독립 실행합니다. 기존 CLI 로그인을 사용하며 직접 모델 API나 다른 실행기로 자동 전환하지 않습니다. 비대화형 `exec --json`의 완료 이벤트와 최종 응답, 실제 모델·추론 인자, 원본 stdout 해시를 영수증으로 남깁니다. 응답 schema가 있으면 빈 호출 폴더에 같은 schema 파일을 만들고 `--output-schema`로 전달합니다. 불완전 완료·실패 이벤트·예상하지 않은 도구 사용은 성공으로 처리하지 않습니다. Codex strict 전송이 지원하지 않는 `uniqueItems`는 전송용 복사본에서만 제외하고, 원래 schema는 프롬프트·원본 요청에 보존합니다. 응답과 재사용 영수증은 원래 전체 schema로 다시 검사하므로 중복·필수 항목 위반은 실패합니다. 전송 schema 해시도 영수증에 결합하며 외부 schema 참조를 가져오지 않습니다.

이 경로는 사용자 전역 실행 설정·프로젝트 지침을 불러오지 않고, 읽기 전용 임시 작업공간에서 문서 응답만 요청합니다. 모델·추론 강도는 명시적인 호출 인자로 지정합니다. JSONL에 서버가 실제 모델 이름을 별도로 보고하지 않는 경우, 영수증은 명시한 CLI 인자와 완료를 입증하며 서버 내부의 모델 식별자를 독립 확인했다는 뜻은 아닙니다.

모델을 바꾸면 재사용 입력이 달라집니다. 기존 모델 원고나 영수증의 모델명을 새 모델로 고치지 말고, 현재 입력·정책·실행 출처를 확인해 필요한 생성·검토를 수행하세요.

기준: [GPT-6.1 Terra](https://developers.openai.com/api/docs/models/gpt-6.1-terra), [Codex 비대화형 실행](https://learn.chatgpt.com/docs/non-interactive-mode).

## 호출·응답 검증

| 항목 | 동작 |
|---|---|
| 입력 전달 | 규칙·소스 발췌·출력 schema를 표준입력으로 전달합니다. 긴 한글 입력을 명령줄 인자로 넣지 않습니다. |
| 작업 위치 | 소스 checkout과 분리된 빈 임시 작업 폴더에서 호출합니다. Hermes의 도구는 `todo`로 제한하고, Claude Code의 내장 도구·MCP와 OpenCode의 도구 권한을 차단합니다. CLI 자체의 전역 설정·훅·플러그인은 운영 환경에서 관리해야 합니다. |
| 모델 설정 | `model`·`args` 또는 CLI 설정을 사용합니다. API 전용 `temperature`, `num_ctx`, `think`, `max_output_tokens`를 CLI 옵션으로 자동 변환하지 않습니다. |
| 실패 | 실행 파일 누락·시간 초과·종료 코드 오류·빈 응답·JSON 완료 상태 오류는 실패합니다. CLI가 생성한 내용에도 기존 문서·근거·노드 한도 검사를 적용합니다. |
| 증거 | `build/prompts/calls/`의 요청·응답·receipt와 `build/prompts/cli/`의 CLI 출력을 보관합니다. receipt의 `transport: cli`, `cli_call: true`, `http_call: false`는 생성기가 CLI를 실행했다는 뜻입니다. CLI 내부의 HTTP 호출 수는 뜻하지 않습니다. 모델 생략 시에는 `model_selection: cli-default`로 기록합니다. |

설계 답변의 본문·근거 구조 검사는 통과했지만 출처 대조 응답의 JSON 형식만 잘못된 경우에는, 같은 실행의 후보를 메모리에 유지하고 기존 재시도 한도 안에서 CLI로 대조만 다시 요청합니다. 근거가 부족하다는 판정은 기존처럼 답변을 다시 생성합니다. 이전 실행의 저장 응답을 실패한 CLI 대신 사용하는 동작은 아닙니다.

`automation.hermes`라는 기존 설정 키는 호환성을 위해 유지합니다. `agent.kind: cli`이면 설명 재검토와 누락 보완도 선택한 `agent.runner`를 사용합니다. 예전에 지정한 `automation.hermes.command`는 CLI 모드에서 거절합니다. 해당 값을 제거하고 실행 경로를 `agent.command`로 통일합니다.

직접 API 비교 시험은 별도 설정에 `kind: ollama` 또는 `openai-compatible`과 `allow_direct_api: true`를 모두 명시해야 합니다. CLI 실패의 대체 경로로 사용하지 않습니다. `dry-run`과 `response-bundle`은 모델을 자동 호출하지 않으므로 CLI 재현 성공으로 보고하지 않습니다. 기존 HTTP 응답을 가져오는 `repair_reader --seed`는 CLI 원응답 재사용을 지원하지 않습니다.

## 공개 입력으로 재생성 시험

저장소 또는 반입본에서 새 출력 경로로 실행합니다. 다음 `<선택한 runner>`를 `hermes`, `opencode`, `claude`, `codex` 중 하나로 바꾸세요. 이 도구의 `--runner`·`--model`·`--cli-arg`는 시험 전용 인자이며 운영 `sdd.yaml`의 `agent`를 자동으로 읽지 않습니다. 아래 명령은 선택한 CLI의 기본 모델·설정을 사용합니다.

```text
python tools/evaluate_visuals.py --out build/cli-replay --runner <선택한 runner> --with-prose
```

실행별 모델은 `--model`, 추가 인자는 반복 가능한 `--cli-arg`로 전달합니다. 예를 들어 사용자가 공개 Hermes/Qwen 시험을 선택했을 때만 다음을 사용합니다.

```bash
python tools/evaluate_visuals.py --out build/hermes-replay --runner hermes --model qwen3.5:9b-ctx64k --cli-arg=--provider --cli-arg=custom --cli-arg=--reasoning --cli-arg=high --with-prose
```

공개 mini HAL의 두 Git 커밋에서 문서 답변과 그림을 생성하고, 조건 변경 후 재생성·이전 사이트 보존·원응답 해시를 검사합니다. 실제 CLI 호출 결과와 테스트 대역의 자동 검사를 구분합니다. 이 시험은 사내 HAL·실기기·사람 승인 검증이 아닙니다.

비대화형 실행 형식의 기준은 [Hermes CLI](https://hermes-agent.nousresearch.com/docs/user-guide/cli/), [OpenCode CLI](https://opencode.ai/docs/cli/), 설치된 Claude Code의 `claude --help`입니다. CLI 버전이 다르면 `command`와 `args`를 확인하고 공개 입력부터 재시험합니다.

다음 단계는 [사내 에이전트 실행 절차](agent.md)에 따라 추출·생성·검증을 연결하는 것입니다.
