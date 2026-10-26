# 문서 생성 CLI 선택

**기본 Hermes CLI로 실행하고, 필요할 때 `agent.runner`를 `opencode` 또는 `claude`로 바꾸세요.** 모델과 제공자는 선택한 CLI의 설정을 사용합니다. 생성기는 해당 CLI를 독립적으로 실행하며 다른 CLI나 모델 API로 자동 전환하지 않습니다.

```yaml
agent:
  kind: cli
  runner: hermes
  timeout_sec: 600
  max_input_chars: 30000
```

## 실행기와 모델 변경

1. 사용할 CLI를 설치하고 사내에서 허용한 모델·제공자·인증을 해당 CLI에 설정합니다. Hermes 뒤에서 Qwen을 제공하는 서버로 Ollama를 사용할 수 있습니다. 이 경우에도 호출 순서는 생성기 → Hermes CLI → Qwen입니다.
2. `sdd.local.yaml`에서 `agent.runner`를 선택합니다. `hermes`, `opencode`, `claude`를 지원합니다. OpenCode나 Claude Code를 선택하면 Hermes를 거치지 않습니다.
3. `uv run sdd --config <CFG> doctor`를 실행합니다. CLI 모드의 doctor는 실행 파일과 버전만 확인하며 모델 호출 성공을 뜻하지 않습니다.
4. 공개 입력 또는 사내에서 허용된 입력으로 `generate`를 실행하고 원응답·검사 결과를 확인합니다. CLI가 없거나 실패하면 설치·인증·모델 설정을 고친 뒤 같은 실행기로 다시 실행합니다.

실행별 모델을 지정하려면 해당 CLI가 받는 모델 ID를 `model`에 적습니다. 생략하면 CLI의 기본값을 유지하며 Qwen이나 특정 제공자를 자동으로 선택하지 않습니다. 제공자나 추론 설정 등은 CLI별 인자를 `args` 목록에 넣습니다.

```yaml
agent:
  kind: cli
  runner: hermes
  model: qwen3.5:9b
  args: [--provider, custom, --reasoning, none]
```

OpenCode에서는 `runner: opencode`와 해당 CLI의 `provider/model` ID를, Claude Code에서는 `runner: claude`와 해당 CLI가 지원하는 모델 ID를 사용합니다. 모델 제공자와 지원 모델은 CLI별로 다르므로 모든 CLI가 모든 모델을 지원한다고 가정하지 않습니다. 위 Qwen 설정은 공개 시험 예제이며 사내 기본 모델을 지정하지 않습니다.

CLI 실행 파일이나 사내 실행 래퍼를 지정해야 한다면 `command: ["/approved/path/hermes"]`처럼 실행 접두사를 인자 목록으로 적습니다. 생성기가 각 CLI의 비대화형 옵션을 이어 붙입니다. 셸 명령 문자열을 넣지 않으며 인증 토큰은 `args`나 `command`에 넣지 않습니다. 각 CLI에서 승인된 인증 수단으로 관리합니다.

## 호출·응답 검증

| 항목 | 동작 |
|---|---|
| 입력 전달 | 규칙·소스 발췌·출력 schema를 표준입력으로 전달합니다. 긴 한글 입력을 명령줄 인자로 넣지 않습니다. |
| 작업 위치 | 소스 checkout과 분리된 빈 임시 작업 폴더에서 호출합니다. Hermes의 도구는 `todo`로 제한하고, Claude Code의 내장 도구·MCP와 OpenCode의 도구 권한을 차단합니다. CLI 자체의 전역 설정·훅·플러그인은 운영 환경에서 관리해야 합니다. |
| 모델 설정 | `model`·`args` 또는 CLI 설정을 사용합니다. API 전용 `temperature`, `num_ctx`, `think`, `max_output_tokens`를 CLI 옵션으로 자동 변환하지 않습니다. |
| 실패 | 실행 파일 누락·시간 초과·종료 코드 오류·빈 응답·JSON 완료 상태 오류는 실패합니다. CLI가 생성한 내용에도 기존 문서·근거·노드 한도 검사를 적용합니다. |
| 증거 | `build/prompts/calls/`의 요청·응답·receipt와 `build/prompts/cli/`의 CLI 출력을 보관합니다. receipt의 `transport: cli`, `cli_call: true`, `http_call: false`는 생성기가 CLI를 실행했다는 뜻입니다. CLI 내부의 HTTP 호출 수는 뜻하지 않습니다. 모델 생략 시에는 `model_selection: cli-default`로 기록합니다. |

`automation.hermes`라는 기존 설정 키는 호환성을 위해 유지합니다. `agent.kind: cli`이면 설명 재검토와 누락 보완도 선택한 `agent.runner`를 사용합니다. 예전에 지정한 `automation.hermes.command`는 CLI 모드에서 거절합니다. 해당 값을 제거하고 실행 경로를 `agent.command`로 통일합니다.

직접 API 비교 시험은 별도 설정에 `kind: ollama` 또는 `openai-compatible`과 `allow_direct_api: true`를 모두 명시해야 합니다. CLI 실패의 대체 경로로 사용하지 않습니다. `dry-run`과 `response-bundle`은 모델을 자동 호출하지 않으므로 CLI 재현 성공으로 보고하지 않습니다. 기존 HTTP 응답을 가져오는 `repair_reader --seed`는 CLI 원응답 재사용을 지원하지 않습니다.

## 공개 입력으로 재생성 시험

저장소 또는 반입본에서 새 출력 경로로 실행합니다. Qwen 공개 시험에만 필요한 옵션을 명시하며, CLI의 기본 모델로 시험하려면 모델·추가 인자를 생략합니다.

```bash
python tools/evaluate_visuals.py --out build/hermes-replay --runner hermes --model qwen3.5:9b --cli-arg=--provider --cli-arg=custom --cli-arg=--reasoning --cli-arg=none --with-prose
```

공개 mini HAL의 두 Git 커밋에서 문서 답변과 그림을 생성하고, 조건 변경 후 재생성·이전 사이트 보존·원응답 해시를 검사합니다. 실제 CLI 호출 결과와 테스트 대역의 자동 검사를 구분합니다. 이 시험은 사내 HAL·실기기·사람 승인 검증이 아닙니다.

비대화형 실행 형식의 기준은 [Hermes CLI](https://hermes-agent.nousresearch.com/docs/user-guide/cli/), [OpenCode CLI](https://opencode.ai/docs/cli/), 설치된 Claude Code의 `claude --help`입니다. CLI 버전이 다르면 `command`와 `args`를 확인하고 공개 입력부터 재시험합니다.

다음 단계는 [사내 에이전트 실행 절차](agent.md)에 따라 추출·생성·검증을 연결하는 것입니다.
