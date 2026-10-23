"""절 단위 승인 장부: 사람 검토 기록과 게시 정책의 근거.

파이프라인의 `ok`/`mapped` 는 자동 검사 결과일 뿐 사람의 승인이 아니다. 이 모듈은 사람이
검토를 마친 기록(누가, 언제, 어떤 커밋 기준, 어떤 본문)을 원고 옆의 장부에 남기고,
사이트 빌드와 범위 검사 관문이 그 기록을 읽게 한다.

- 승인은 사람이 `sdd accept` 로 실행한다. 파이프라인이 자동으로 승인을 기록하지 않는다.
- 승인은 본문 해시에 붙는다. 본문이 한 글자라도 바뀌면 승인은 stale 이 되고, 근거 재검증만
  거쳐 커밋을 이월한 원고(본문 동일)는 승인이 유지된다.
- 범위 검토 항목(coverage findings)은 이름 기준으로 승인·보류를 기록한다. 승인한 항목은
  `--fail-on-coverage-gap` 관문에서 제외되어, 관문이 늘 빨간색이 되는 것을 막는다.
  보류(deferred)는 확인만 한 상태이므로 관문을 통과시키지 않는다.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Config

LEDGER_NAME = "approvals.json"

_FRONTMATTER = re.compile(r"\A---\r?\n.*?\r?\n---\r?\n", re.S)


def ledger_path(cfg: Config) -> Path:
    # 원고와 함께 버전 관리되도록 sdd_dir 에 둔다. 승인은 특정 본문에 대한 기록이기 때문이다.
    return cfg.sdd_dir / LEDGER_NAME


def load(cfg: Config) -> dict[str, Any]:
    path = ledger_path(cfg)
    if not path.exists():
        return {"schema": 1, "pages": {}, "findings": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != 1:
        raise RuntimeError(f"지원하지 않는 승인 장부 schema 입니다: {path}")
    data.setdefault("pages", {})
    data.setdefault("findings", {})
    return data


def save(cfg: Config, data: dict[str, Any]) -> Path:
    path = ledger_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=1) + "\n",
                    encoding="utf-8", newline="\n")
    return path


def body_hash(text: str) -> str:
    """frontmatter 를 뺀 본문의 해시.

    이월(carryover)은 본문을 그대로 두고 meta 의 기준 커밋만 바꾼다. 승인이 meta 까지 묶으면
    내용이 같은데도 매 커밋마다 승인이 풀리므로, 사람이 읽고 승인한 대상인 본문에만 붙인다.
    """
    body = _FRONTMATTER.sub("", text, count=1)
    return hashlib.sha256(body.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def page_status(ledger: dict[str, Any], rel: str, text: str) -> str:
    """approved | stale | unreviewed. stale 은 승인 이후 본문이 바뀐 상태다."""
    entry = ledger.get("pages", {}).get(rel)
    if not entry:
        return "unreviewed"
    return "approved" if entry.get("content_sha256") == body_hash(text) else "stale"


def approve_page(ledger: dict[str, Any], rel: str, text: str, by: str,
                 source_commit: str = "", note: str = "") -> dict[str, Any]:
    entry = {"approved_by": by,
             "approved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "source_commit": source_commit,
             "content_sha256": body_hash(text)}
    if note:
        entry["note"] = note
    ledger.setdefault("pages", {})[rel] = entry
    return entry


def finding_key(finding: dict[str, Any]) -> str:
    return f"{finding.get('reason')}:{finding.get('kind')}:{finding.get('name')}"


def finding_state(ledger: dict[str, Any], finding: dict[str, Any]) -> str:
    """accepted | deferred | open."""
    entry = ledger.get("findings", {}).get(finding_key(finding))
    return str(entry.get("state")) if entry else "open"


def record_finding(ledger: dict[str, Any], key: str, state: str, by: str, note: str = "") -> dict[str, Any]:
    if state not in ("accepted", "deferred"):
        raise RuntimeError(f"범위 검토 항목의 상태는 accepted 또는 deferred 만 됩니다: {state}")
    entry = {"state": state, "by": by,
             "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if note:
        entry["note"] = note
    ledger.setdefault("findings", {})[key] = entry
    return entry


def open_findings(coverage: dict[str, Any], ledger: dict[str, Any],
                  passed: set[str] | frozenset[str] = frozenset()) -> list[dict[str, Any]]:
    """승인(accepted)되지 않은 범위 검토 항목. 관문(종료 코드 2)은 이 목록으로 판정한다.

    passed 는 설정이 허용한 LLM "범위 밖" 판정의 장부 키다(coverage_triage.passed). 승인이 아니므로
    장부에는 기록하지 않고, 관문 판정에서만 뺀다.
    """
    return [f for f in (coverage.get("findings") or [])
            if finding_state(ledger, f) != "accepted" and finding_key(f) not in passed]
