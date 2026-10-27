"""사내 LLM 호출 계층.

- cli               : 기본 Hermes CLI. OpenCode 또는 Claude Code를 독립적으로 선택한다.
- ollama            : 명시적으로 허용한 API 비교 시험 (`/api/chat`).
- openai-compatible : 명시적으로 허용한 `/v1/chat/completions` API 비교 시험.
                      토큰이 필요하면 환경 변수 SDD_AGENT_API_KEY 로 넘긴다. 설정 파일에는 두지 않는다.
- dry-run           : 호출하지 않고 build/prompts/ 에 프롬프트를 기록한다. 파이프라인 점검용.
- response-bundle   : 입력 해시에 연결된 LLM 응답을 파일로 교환한다. 모델 실행은 별도 실행기 책임이다.

사내 소스와 파생 데이터는 사내 경계 안에서 처리해야 한다. 연결 대상과 파일 교환 실행기는 운영 환경에서 관리한다.
"""

from __future__ import annotations

import json
import hashlib
import os
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .config import AgentConfig
from .agent_errors import AgentError

LIVE_KINDS = ('cli', 'ollama', 'openai-compatible')
SCHEMA_KINDS = ('cli', 'ollama', 'response-bundle')


class Agent:
    def __init__(self, cfg: AgentConfig, dump_dir: Path | None = None):
        self.cfg = cfg
        self.dump_dir = dump_dir
        self._counter = 0
        self._run_id = uuid.uuid4().hex
        self._transport_metadata = {}

    def chat(self, system: str, user: str, tag: str = "prompt", response_schema: dict | None = None) -> str:
        self._counter += 1
        self._transport_metadata = {}
        request = {'system': system, 'user': user, 'response_schema': response_schema}
        request_hash = hashlib.sha256(json.dumps(request, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        if self.dump_dir:
            self.dump_dir.mkdir(parents=True, exist_ok=True)
            (self.dump_dir / f"{self._counter:03d}_{tag}.md").write_text(
                f"<!-- system -->\n{system}\n\n<!-- user -->\n{user}\n", encoding="utf-8")
            if response_schema and self.cfg.kind in SCHEMA_KINDS:
                (self.dump_dir / f"{self._counter:03d}_{tag}.schema.json").write_text(
                    json.dumps(response_schema, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        kind = self.cfg.kind
        if kind in ('ollama', 'openai-compatible') and not self.cfg.allow_direct_api:
            raise AgentError('직접 모델 API 호출은 비활성화되어 있습니다. agent.kind: cli를 사용하세요. 별도 비교 시험에만 allow_direct_api: true를 명시하세요.')
        if kind == "dry-run":
            return f"(dry-run) {tag}: LLM 을 호출하지 않았습니다. 프롬프트는 build/prompts/ 에 기록했습니다."
        if kind == 'cli':
            from . import cli_agent
            try:
                text, self._transport_metadata = cli_agent.chat(self.cfg, system, user, response_schema, self.dump_dir)
            except (OSError, ValueError, RuntimeError) as exc:
                raise AgentError(str(exc)) from exc
        elif kind == "ollama":
            text = self._ollama(system, user, response_schema) if response_schema else self._ollama(system, user)
        elif kind == "openai-compatible":
            text = self._openai(system, user)
        elif kind == 'response-bundle':
            text = self._response_bundle(system, user, response_schema)
        else:
            raise AgentError(f"알 수 없는 agent.kind: {kind}")
        if self.dump_dir:
            # 검증 전 원문. 왜 needs-review 가 됐는지 볼 때 필요하다.
            (self.dump_dir / f"{self._counter:03d}_{tag}.response.md").write_text(text + "\n", encoding="utf-8")
            # Immutable per-invocation receipts distinguish real HTTP calls from
            # imported responses, even when the caller retries into the same dir.
            archive = self.dump_dir / 'calls' / self._run_id
            archive.mkdir(parents=True, exist_ok=True)
            prefix = archive / f'{self._counter:03d}'
            prefix.with_suffix('.request.json').write_text(
                json.dumps(request, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
            prefix.with_suffix('.response.txt').write_text(text, encoding='utf-8', newline='\n')
            receipt = {
                'schema': 1, 'tag': tag, 'completed_at': datetime.now(timezone.utc).isoformat(),
                'transport': kind, 'model': self.cfg.model,
                'http_call': kind in ('ollama', 'openai-compatible'),
                'cli_call': kind == 'cli',
                'request_sha256': request_hash,
                'response_sha256': hashlib.sha256(text.encode()).hexdigest(),
                'settings': {k: getattr(self.cfg, k) for k in (
                    'temperature', 'think', 'num_ctx', 'max_output_tokens')},
                'provider': self._transport_metadata,
                'human_review': 'pending',
            }
            prefix.with_suffix('.receipt.json').write_text(
                json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        if (self._transport_metadata.get('done_reason') == 'length'
                or self._transport_metadata.get('finish_reason') == 'length'):
            raise AgentError('모델이 출력 토큰 한도에 도달했습니다. 부분 답변을 사용하지 않습니다. '
                             'max_output_tokens 또는 질문·추론 설정을 확인하세요.')
        return text

    def ping(self) -> str:
        """doctor 용. 도달 가능하면 한 줄 요약, 아니면 예외."""
        if self.cfg.kind == "dry-run":
            return "dry-run (호출 없음)"
        if self.cfg.kind == 'cli':
            from . import cli_agent
            try:
                return cli_agent.check(self.cfg)
            except (OSError, ValueError, RuntimeError) as exc:
                raise AgentError(str(exc)) from exc
        if self.cfg.kind in ('ollama', 'openai-compatible') and not self.cfg.allow_direct_api:
            raise AgentError('직접 모델 API 호출은 비활성화되어 있습니다. agent.kind: cli를 사용하세요.')
        if self.cfg.kind == 'response-bundle':
            if not self.cfg.response_dir:
                raise AgentError('response-bundle에는 agent.response_dir가 필요합니다.')
            return f'response-bundle/{self.cfg.model} (파일 교환; 모델 접속 검사는 아님)'
        if self.cfg.kind not in ('ollama', 'openai-compatible'):
            raise AgentError(f'알 수 없는 agent.kind: {self.cfg.kind}')
        if self.cfg.kind == "ollama":
            data = self._get(f"{self.cfg.base_url}/api/tags")
            names = [m.get("name", "") for m in data.get("models", [])]
            found = self.cfg.model in names
            return f"ollama 모델 {len(names)} 개, {self.cfg.model} {'있음' if found else '없음'}"
        data = self._get(f"{self.cfg.base_url}/v1/models")
        names = [m.get("id", "") for m in data.get("data", [])]
        return f"openai-compatible 모델 {len(names)} 개, {self.cfg.model} {'있음' if self.cfg.model in names else '목록에 없음'}"

    # ---- transports ------------------------------------------------------

    def _response_bundle(self, system, user, response_schema):
        from .response_bundle import exchange
        return exchange(self.cfg, system, user, response_schema)

    def _ollama(self, system: str, user: str, response_schema: dict | None = None) -> str:
        body: dict = {
            "model": self.cfg.model,
            "stream": False,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "options": {"temperature": self.cfg.temperature},
            # Qwen3 계열은 기본으로 긴 thinking 을 먼저 생성한다. 문서 서술에는 도움이 안 되고 시간만 든다.
            "think": self.cfg.think,
        }
        if self.cfg.num_ctx:
            body["options"]["num_ctx"] = self.cfg.num_ctx
        if self.cfg.max_output_tokens:
            body["options"]["num_predict"] = self.cfg.max_output_tokens
        if response_schema:
            body['format'] = response_schema
        data = self._post(f"{self.cfg.base_url}/api/chat", body)
        self._transport_metadata = {k: data[k] for k in (
            'model', 'created_at', 'done', 'done_reason', 'total_duration',
            'load_duration', 'prompt_eval_count', 'prompt_eval_duration',
            'eval_count', 'eval_duration') if k in data}
        try:
            content = str(data["message"]["content"]).strip()
            return content
        except (KeyError, TypeError) as e:
            raise AgentError(f"ollama 응답 형식이 예상과 다릅니다: {data}") from e

    def _openai(self, system: str, user: str) -> str:
        body: dict = {
            "model": self.cfg.model,
            "temperature": self.cfg.temperature,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        if self.cfg.max_output_tokens:
            body["max_tokens"] = self.cfg.max_output_tokens
        data = self._post(f"{self.cfg.base_url}/v1/chat/completions", body)
        self._transport_metadata = {k: data[k] for k in ('model', 'id', 'usage') if k in data}
        try:
            self._transport_metadata['finish_reason'] = data['choices'][0].get('finish_reason')
            return str(data["choices"][0]["message"]["content"]).strip()
        except (KeyError, IndexError, TypeError) as e:
            raise AgentError(f"openai-compatible 응답 형식이 예상과 다릅니다: {data}") from e

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        key = os.environ.get(self.cfg.api_key_env)
        if key:
            h["Authorization"] = f"Bearer {key}"
        return h

    def _post(self, url: str, body: dict) -> dict:
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                     headers=self._headers(), method="POST")
        return self._send(req)

    def _get(self, url: str) -> dict:
        req = urllib.request.Request(url, headers=self._headers(), method="GET")
        return self._send(req)

    def _send(self, req: urllib.request.Request) -> dict:
        try:
            with urllib.request.urlopen(req, timeout=self.cfg.timeout_sec) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise AgentError(f"{req.full_url} -> HTTP {e.code}: {e.read()[:200]!r}") from e
        except urllib.error.URLError as e:
            raise AgentError(f"{req.full_url} 에 연결하지 못했습니다: {e.reason}") from e
        except (ValueError, UnicodeDecodeError) as e:      # 200 응답이지만 JSON 이 아닌 경우
            raise AgentError(f"{req.full_url} 의 응답이 JSON 이 아닙니다: {e}") from e
