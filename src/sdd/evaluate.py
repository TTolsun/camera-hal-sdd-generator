"""Compare configured narration models on identical source-bound topic prompts.

Run with python -m sdd.evaluate. Results are experiments, never approvals.
"""
from __future__ import annotations

import argparse
import copy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
import time
import urllib.request

from .budget import fit
from .config import load
from .evidence import collect, topic_blocks
from .facts.model import KnowledgeModel
from .generate import Generator
from .llm import Agent, AgentError


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class EvaluationGenerator(Generator):
    def _record_review(self, tag, text, verdict, omitted, mode="generated-prose"):
        # The experiment must not overwrite production review records.
        pass


class RecordingAgent(Agent):
    def __init__(self, cfg, output: Path, expected: dict):
        super().__init__(cfg, output)
        self.expected = expected
        self.prompt_hash = ""
        self.response = {}

    def _post(self, url: str, body: dict) -> dict:
        self.response = super()._post(url, body)
        write_json(self.dump_dir / "transport-response.json", self.response)
        return self.response

    def chat(self, system: str, user: str, tag: str = "prompt") -> str:
        prompt = json.dumps([system, user], ensure_ascii=False)
        self.prompt_hash = digest(prompt)
        if tag in self.expected and self.expected[tag] != self.prompt_hash:
            raise ValueError(f"Prompt changed between candidates: {tag}")
        self.expected[tag] = self.prompt_hash
        return super().chat(system, user, tag)


def run(config: Path, models: list[str], cases: list[str], out: Path, repeats: int = 2) -> dict:
    if len(models) < 2 or len(set(models)) != len(models):
        raise ValueError("Choose at least two distinct models")
    if repeats < 1 or not cases or len(set(cases)) != len(cases):
        raise ValueError("Choose unique cases and at least one repeat")
    if out.exists():
        raise ValueError("Use a new output directory; failed samples must be preserved")
    cfg = load(config)
    if cfg.agent.kind not in ("ollama", "openai-compatible"):
        raise ValueError("A real configured model endpoint is required")
    cfg.max_retries = 0  # Repair prompts would invalidate the fixed-input comparison.
    model = KnowledgeModel.load(cfg.facts_path)
    if not re.fullmatch(r"[0-9a-f]{40}", str(model.meta.get("source_commit", ""))):
        raise ValueError("A pinned source commit is required")
    collect(cfg, model)
    sections = {s["id"]: s for s in cfg.sections()}
    selected = []
    probe = EvaluationGenerator(cfg, model, Agent(cfg.agent))
    for case in cases:
        if not re.fullmatch(r"[\w-]+/[\w-]+", case):
            raise ValueError(f"Expected section/topic: {case}")
        sid, tid = case.split("/")
        sec = sections[sid]
        topic = next(t for t in sec.get("design_topics", []) if t["id"] == tid)
        blocks, gaps = topic_blocks(model, sid, topic)
        if gaps:
            raise ValueError(" / ".join(gaps))
        reserved = len(probe.system) + len(probe.section_tpl) + len(topic["title"]) + 400
        _, omitted = fit(blocks, cfg.agent.max_input_chars, reserved=reserved)
        if omitted:
            raise ValueError(f"Evidence omitted in {case}: {omitted}")
        selected.append((case, {**sec, "answers": [topic["question"]], "semantic_review": True},
                         topic["title"], blocks))
    identities = {name: {"model": name, "digest": None} for name in models}
    if cfg.agent.kind == "ollama":
        with urllib.request.urlopen(cfg.agent.base_url + "/api/tags", timeout=30) as response:
            installed = {x["name"]: x for x in json.load(response)["models"]}
        for name in models:
            if name not in installed:
                raise ValueError(f"Install the model before evaluation: {name}")
            identities[name] = installed[name]
    out.mkdir(parents=True)
    model.save(out / "facts.json")
    report = {
        "schema": 1, "source_commit": model.meta["source_commit"],
        "input_facts_sha256": hashlib.sha256(cfg.facts_path.read_bytes()).hexdigest(),
        "evidence_facts_sha256": hashlib.sha256((out / "facts.json").read_bytes()).hexdigest(),
        "settings": {k: v for k, v in asdict(cfg.agent).items() if k not in ("base_url", "model")},
        "models": identities, "cases": cases, "repeats": repeats, "repair_retries": 0,
        "human_review": "pending", "samples": [],
        "scope": "Automatic checks are not semantic evaluation or publication approval.",
    }
    expected = {}
    write_json(out / "result.json", report)
    # Alternate model order to reduce systematic warm-cache/order bias.
    for repeat in range(repeats):
        order = list(enumerate(models))
        if repeat % 2:
            order.reverse()
        for index, name in order:
            candidate = copy.deepcopy(cfg.agent)
            candidate.model = name
            for case, sec, title, blocks in selected:
                sample = out / f"model-{index + 1}" / f"repeat-{repeat + 1}" / case.replace("/", "--")
                sample.mkdir(parents=True)
                agent = RecordingAgent(candidate, sample, expected)
                gen = EvaluationGenerator(cfg, model, agent)
                started = time.monotonic()
                item = {"model": name, "repeat": repeat + 1, "case": case,
                        "path": sample.relative_to(out).as_posix()}
                print(f"{name} repeat={repeat + 1} {case}", flush=True)
                try:
                    text, omitted, verdict = gen._ask(case.replace("/", "--"), sec, title, blocks, "")
                    (sample / "processed.md").write_text(text + "\n", encoding="utf-8")
                    item.update(verdict=asdict(verdict), omitted=omitted)
                    reason = agent.response.get("done_reason")
                    choices = agent.response.get("choices", [])
                    if choices:
                        reason = choices[0].get("finish_reason")
                    item["finish_reason"] = reason
                    if reason in ("length", "max_tokens"):
                        item["verdict"]["ok"] = False
                        item["verdict"]["notes"].append("Output token limit reached")
                except AgentError as exc:
                    # Do not record response bodies/endpoints from HTTP errors in reports.
                    item.update(error=type(exc).__name__, verdict={"ok": False})
                item.update(seconds=round(time.monotonic() - started, 2), prompt_sha256=agent.prompt_hash)
                report["samples"].append(item)
                write_json(out / "result.json", report)
    report["prompt_sha256"] = expected
    write_json(out / "result.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--model", action="append", required=True)
    parser.add_argument("--case", action="append", required=True, help="section/topic")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=2)
    args = parser.parse_args()
    result = run(args.config, args.model, args.case, args.out, args.repeats)
    return 2 if any("error" in item for item in result["samples"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
