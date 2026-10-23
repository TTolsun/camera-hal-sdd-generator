"""사내 LLM 호출 계층.

- ollama            : 로컬 Ollama (`/api/chat`). Qwen, Hermes 모두 이 경로로 운영 가능하다.
- openai-compatible : Hermes 서비스나 vLLM 처럼 `/v1/chat/completions` 를 제공하는 사내 게이트웨이.
                      토큰이 필요하면 환경 변수 SDD_AGENT_API_KEY 로 넘긴다. 설정 파일에는 두지 않는다.
- dry-run           : 호출하지 않고 build/prompts/ 에 프롬프트를 기록한다. 파이프라인 점검용.

외부 SaaS 는 지원하지 않는다. 코드가 사내 밖으로 나가면 안 된다.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from .config import AgentConfig


class AgentError(RuntimeError):
    pass


class Agent:
    def __init__(self, cfg: AgentConfig, dump_dir: Path | None = None):
        self.cfg = cfg
        self.dump_dir = dump_dir
        self._counter = 0

    def chat(self, system: str, user: str, tag: str = "prompt") -> str:
        self._counter += 1
        if self.dump_dir:
            self.dump_dir.mkdir(parents=True, exist_ok=True)
            (self.dump_dir / f"{self._counter:03d}_{tag}.md").write_text(
                f"<!-- system -->\n{system}\n\n<!-- user -->\n{user}\n", encoding="utf-8")
        kind = self.cfg.kind
        if kind == "dry-run":
            return f"(dry-run) {tag}: LLM 을 호출하지 않았습니다. 프롬프트는 build/prompts/ 에 기록했습니다."
        if kind == "ollama":
            text = self._ollama(system, user)
        elif kind == "openai-compatible":
            text = self._openai(system, user)
        else:
            raise AgentError(f"알 수 없는 agent.kind: {kind}")
        if self.dump_dir:
            # 검증 전 원문. 왜 needs-review 가 됐는지 볼 때 필요하다.
            (self.dump_dir / f"{self._counter:03d}_{tag}.response.md").write_text(text + "\n", encoding="utf-8")
        return text

    def ping(self) -> str:
        """doctor 용. 도달 가능하면 한 줄 요약, 아니면 예외."""
        if self.cfg.kind == "dry-run":
            return "dry-run (호출 없음)"
        if self.cfg.kind == "ollama":
            data = self._get(f"{self.cfg.base_url}/api/tags")
            names = [m.get("name", "") for m in data.get("models", [])]
            found = self.cfg.model in names
            return f"ollama 모델 {len(names)} 개, {self.cfg.model} {'있음' if found else '없음'}"
        data = self._get(f"{self.cfg.base_url}/v1/models")
        names = [m.get("id", "") for m in data.get("data", [])]
        return f"openai-compatible 모델 {len(names)} 개, {self.cfg.model} {'있음' if self.cfg.model in names else '목록에 없음'}"

    # ---- transports ------------------------------------------------------

    def _ollama(self, system: str, user: str) -> str:
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
        data = self._post(f"{self.cfg.base_url}/api/chat", body)
        try:
            return str(data["message"]["content"]).strip()
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
        try:
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
