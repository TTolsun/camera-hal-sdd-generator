"""Exact request-bound file exchange; this adapter does not assert a live call."""
import hashlib
import json
from pathlib import Path

from .agent_errors import AgentError


def exchange(cfg, system, user, response_schema):
    if not cfg.response_dir:
        raise AgentError('response-bundle에는 agent.response_dir가 필요합니다.')
    request = {'system': system, 'user': user, 'response_schema': response_schema}
    key = hashlib.sha256(json.dumps(request, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    directory = Path(cfg.response_dir)
    directory.mkdir(parents=True, exist_ok=True)
    envelope = {'schema': 1, 'model': cfg.model, 'request_sha256': key}
    (directory / f'{key}.request.json').write_text(json.dumps(envelope | request, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    path = directory / f'{key}.response.json'
    if not path.exists():
        raise AgentError(f'현재 입력에 대응하는 LLM 응답이 없습니다: {path}')
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, dict) or any(data.get(k) != v for k, v in envelope.items()):
            raise ValueError('입력 지문·모델·형식 버전이 다릅니다.')
        if not isinstance(data.get('response'), str) or not data['response'].strip():
            raise ValueError('응답 본문이 비었습니다.')
    except (ValueError, OSError) as exc:
        raise AgentError(f'LLM 응답 파일을 사용할 수 없습니다: {path}: {exc}') from exc
    return data['response'].strip()

