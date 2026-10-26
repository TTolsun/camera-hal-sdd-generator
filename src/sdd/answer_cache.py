"""Opt-in checkpoints for validated Ollama answers within one source revision.

The cache is a local retry optimization, not evidence or human approval. A new
revision, question, source passage, model setting or policy requires a new call.
Cached text is passed through the same validators as a fresh HTTP response.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import urllib.request


def model_digest(agent):
    """An alias alone cannot identify weights after an Ollama model update."""
    try:
        with urllib.request.urlopen(agent.base_url.rstrip('/')+'/api/tags', timeout=5) as response:
            models = json.load(response)['models']
        names = {agent.model, agent.model + ':latest'}
        return next((m['digest'] for m in models if m.get('name') in names and m.get('digest')), None)
    except (OSError, ValueError, KeyError, TypeError):
        return None  # Optional optimization must not require a new service API.


def checkpoint(cfg, commit, system, user, options):
    if cfg.agent.kind != 'ollama' or not cfg.agent.allow_direct_api or not (cfg.raw.get('review') or {}).get('answer_cache', False):
        return None
    digest = model_digest(cfg.agent)
    if not digest:
        return None
    identity = dict(commit=commit, system=system, user=user, options=options, model_digest=digest,
                    agent={key: getattr(cfg.agent, key) for key in
                           ('kind', 'model', 'base_url', 'temperature', 'think', 'num_ctx', 'max_output_tokens')})
    key = hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return cfg.build_dir / 'validated-answers' / f'{key}.json'


def read(path):
    if path is None or not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        text = data['response']
        if isinstance(text, str) and hashlib.sha256(text.encode()).hexdigest() == data['sha256']:
            return text
    except (ValueError, KeyError, TypeError, OSError):
        pass
    return None


def save(path, response):
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    from pathlib import Path
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as out:
        temporary = Path(out.name)
        json.dump({'response': response, 'sha256': hashlib.sha256(response.encode()).hexdigest()},
                  out, ensure_ascii=False)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
