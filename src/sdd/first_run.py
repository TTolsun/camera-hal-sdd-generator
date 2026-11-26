"""Prepare missing design inputs from revision-pinned source, using the configured CLI."""
from __future__ import annotations

from collections import defaultdict
from itertools import groupby, islice
import json
from pathlib import PurePosixPath
import re

from .evidence_span import select_span
from .source_git import file_at, resolve_commit
from .state_io import save
from .first_run_catalog import SCHEMA, SYSTEM, _catalog, _fact_inputs, _identity, _key, _response, catalog_path, enabled



# Portable retrieval cues. Their purpose is to find excerpts, never to infer
# that a given implementation actually provides an operation.
CUES = {
    "capabilities": "camera stream device configure capture format",
    "benefits": "camera stream device configure capture format",
    "integration": "open init configure start queue process stop close callback",
    "inputs": "configure validate stream format request buffer error",
    "ownership": "request buffer alloc free release return reuse fence ownership cancel complete",
    "completion": "stop flush cancel abort complete finish queue request pending status buffer",
    "failure": "fail error invalid cancel timeout reject status return recovery",
    "constraints": "check supported validate configure format capability error",
    "verification": "test assert trace status fail error flush stop cancel callback",
    "entry": "camera open create init configure start",
    "responsibility": "interface device manager pipeline handler camera callback",
    "boundaries": "queue callback emit notify IPC request buffer",
    "lifecycle": "open init configure start stop flush destroy release",
    "concurrency": "thread mutex lock wait signal queue sync callback",
}


def pending(cfg, sections, impact=None):
    if not enabled(cfg):
        return []
    return [(section, topic) for section in cfg.sections()
            if section.get("design_generation") == "llm"
            and (not sections or section["id"] in sections)
            and (not impact or section["id"] in impact.sections)
            for topic in section.get("design_topics", [])
            if topic.get("sources") == [] and not any(key in topic for key in
                ("parts", "explanation", "product", "statements", "narration", "answer_contract"))]


def source_commit(cfg, model):
    commit = model.meta.get("source_commit")
    if (not isinstance(commit, str) or not re.fullmatch("[0-9a-f]{40}", commit)
            or resolve_commit(cfg.source_root, "HEAD") != commit):
        raise ValueError("첫 실행 입력을 준비하기 전에 현재 Git HEAD에서 facts를 다시 추출하세요.")
    return commit


def extend_impact(cfg, report):
    """Refresh existing auto-bound manuscripts when their revision/catalog changes."""
    from .config import section_output
    for section, topic in pending(cfg, None):
        if (cfg.sdd_dir / section_output(section)).is_file():
            report.sections.setdefault(section["id"], []).append(
                f"첫 실행 입력 재검증 필요: {topic['id']}")


def _locations(model):
    by_file = defaultdict(dict)

    def add(loc, name, definition=False):
        if not loc or loc.line < 1:
            return
        path = PurePosixPath(loc.file)
        if not path.parts or path.is_absolute() or ".." in path.parts or ":" in loc.file or "\\" in loc.file:
            return
        current = by_file[loc.file].get(loc.line)
        if current is None or (definition, len(name), name) > current:
            by_file[loc.file][loc.line] = (definition, len(name), name)

    for cls in model.classes.values():
        add(cls.loc, cls.name)
        for method in cls.methods:
            name = f"{cls.name}::{method.name}"
            add(method.loc, name)
            add(method.def_loc, name, True)
    for function in model.functions.values():
        add(function.loc, function.name)
        add(function.def_loc, function.name, True)
    for scenario in model.scenarios.values():
        for message in scenario.messages:
            add(message.loc, f"{message.src}::{message.name}")
    for file in model.meta.get("parsed_files", ()):
        # Enum documentation can live in a compiled file without a function.
        path = PurePosixPath(file)
        if path.parts and not path.is_absolute() and ".." not in path.parts and not re.search(r"[:\\\x00\r\n]", file):
            by_file.setdefault(file, {})
    return by_file


def _window(text, line):
    lines = text.splitlines()
    if not 1 <= line <= len(lines):
        return None
    hit = line - 1
    left, right = max(0, hit - 3), min(len(lines), hit + 24)
    current = lines[hit].lstrip()
    if current.startswith(("*", "/*")):
        # Include the contract as a unit, e.g. all fields of a status enum.
        # A long comment is centred on the matched condition below.
        for i in range(hit, max(-1, hit - 65), -1):
            if "/*" in lines[i]:
                left = i
                break
            if i != hit and "*/" in lines[i]:
                break
        for i in range(hit, min(len(lines), hit + 65)):
            if "*/" in lines[i]:
                right = i + 1
                break
    else:
        # End at the current definition/declaration instead of including the
        # next function merely because it fits the transport budget.
        if current.rstrip().endswith(";"):
            right = hit + 1
        else:
            for i in range(hit + 1, right):
                if lines[i].startswith("}"):
                    right = i + 1
                    break
    if len("\n".join(lines[left:line])) > 1150:
        left = max(0, hit - 3)
    while right > line and len("\n".join(lines[left:right])) > 1800:
        right -= 1
    excerpt = "\n".join(lines[left:right]).strip("\n")
    if len(excerpt) > 1900:
        return None
    snippet = excerpt.splitlines()
    if len(snippet) == 1:
        # The anchor format permits two nonempty substrings on the same line.
        for split in range(max(1, len(excerpt) // 2), len(excerpt)):
            start, end = excerpt[:split], excerpt[split:]
            if text.count(start) == 1 and end.strip():
                return excerpt, {"start": start, "end": end}
    for n in range(1, len(snippet)):
        start = "\n".join(snippet[:n])
        if not start.strip() or text.count(start) != 1:
            continue
        for m in range(1, len(snippet) - n + 1):
            end = "\n".join(snippet[-m:])
            if not end.strip() or excerpt.find(end, len(start)) != len(excerpt) - len(end):
                continue
            selector = {"start": start, "end": end}
            a, b = select_span(text, selector)
            if text[a:b] == excerpt:
                return excerpt, selector
    return None


def _scenario_pairs(model):
    definitions = defaultdict(set)
    for cls in model.classes.values():
        for method in cls.methods:
            if method.def_loc:
                target = (method.def_loc.file, method.def_loc.line, f"{cls.name}::{method.name}")
                for owner in {cls.name, cls.name.rsplit("::", 1)[-1]}:
                    definitions[owner, method.name].add(target)
    for function in model.functions.values():
        if function.def_loc:
            target = (function.def_loc.file, function.def_loc.line, function.name)
            for loc in (function.loc, function.def_loc):
                if loc:
                    definitions[PurePosixPath(loc.file).stem, function.name.rsplit("::", 1)[-1]].add(target)

    for scenario in model.scenarios.values():
        for message in scenario.messages:
            if message.note or not message.loc:
                continue
            name = message.name.partition("(")[0].rsplit("::", 1)[-1].strip()
            targets = definitions.get((message.dst, name), ())
            if len(targets) == 1:
                target, = targets
                caller = (message.loc.file, message.loc.line, f"{message.src} → {target[2]}")
                if caller[:2] != target[:2]:
                    yield (scenario.id, caller, target)


def _words(text):
    return set(re.findall(r"[a-z0-9]+", re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text).lower()))


def _candidates(cfg, locations, cache, commit, section, topic, pairs=()):
    from .decision_passages import decision_locations
    from .matching import match_any, watches
    cues = set(" ".join([topic.get("question", ""), topic["id"],
                        *(CUES.get(key, "") for key in topic.get("covers", ()))])
               .lower().replace("-", " ").split())
    ranked = []
    for file, rows in locations.items():
        if match_any(file, section.get("watch_exclude") or []):
            continue
        watched = watches(section, file)
        for line, (definition, _, name) in rows.items():
            score = len(cues & _words(name + " " + file))
            ranked.append((-score, not definition, not watched, file, line, name))
    used = defaultdict(list)
    symbol_rows = ((file, line, name) for _, _, _, file, line, name in sorted(ranked))
    seen = set()

    def candidate(file, line, name):
        if any(abs(line - previous) < 16 for previous in used[file]) or len(used[file]) >= 6:
            return None
        if file not in cache:
            cache[file] = file_at(cfg.source_root, commit, file)
        if cache[file] and (window := _window(cache[file], line)):
            text, anchors = window
            identity = (file, anchors["start"], anchors["end"])
            if identity not in seen:
                return {"file": file, "line": line, "symbol": name, "text": text}, {"file": file, **anchors}
        return None

    def remember(item):
        entry, anchors = item
        file, line = entry["file"], entry["line"]
        used[file].append(line)
        seen.add((file, anchors["start"], anchors["end"]))

    scored = []
    for scenario, caller, target in pairs:
        files = (caller[0], target[0])
        if any(f not in locations or match_any(f, section.get("watch_exclude") or []) for f in files):
            continue
        target_score = len(cues & _words(target[2]))
        score = target_score * 3 + len(cues & _words(scenario + " " + caller[2]))
        if score:
            scored.append((-score, not any(watches(section, f) for f in files), caller, target))
    pair_count = 0
    for _, _, caller, target in sorted(scored):
        if caller[0] == target[0] and abs(caller[1] - target[1]) < 16:
            continue
        call, definition = candidate(*caller), candidate(*target)
        if not call or not definition:
            continue
        pair_count += 1
        for role, item in (("call", call), ("definition", definition)):
            item[0].update(call_pair=pair_count, call_role=role)
            remember(item)
            yield item
        if pair_count == 2:
            break

    decisions = ((file, line, "") for file, line in
                 decision_locations(cfg, commit, locations, section, topic, cache))
    for rows in (decisions, symbol_rows):
        for row in rows:
            if item := candidate(*row):
                remember(item)
                yield item


def _request(cfg, section, topic, candidates, *, visual=False, missing=""):
    from .cli_agent import build_prompt
    displayed, selectors = {}, {}
    requirements = [r["question"] for r in section.get("design_requirements", []) if r["id"] in topic["covers"]]

    def payload():
        return json.dumps({"reader": section.get("reader", section.get("reader_profile", "")),
                           "question": topic["question"], "requirements": requirements,
                           **({"previous_gap": missing[:400]} if missing else {}),
                           "candidates": displayed}, ensure_ascii=False)

    # Keep the full transport envelope, including the response schema, inside
    # the approved input budget. Never slice a candidate's source.
    room = min(900, cfg.agent.max_input_chars // 8) if visual else 0
    groups = defaultdict(list)
    for n, (entry, selector) in enumerate(candidates, 1):
        key = entry.get("candidate_id", f"window-{n}")
        groups[("pair", entry["call_pair"]) if "call_pair" in entry else ("window", key)].append((key, entry, selector))
    for group in groups.values():
        if len(displayed) + len(group) > 16 or ("call_pair" in group[0][1] and len(group) != 2):
            continue
        for key, entry, _ in group:
            displayed[key] = {k: v for k, v in entry.items() if k != "candidate_id"}
        if len(build_prompt(SYSTEM, payload(), SCHEMA)) > cfg.agent.max_input_chars - room:
            for key, _, _ in group:
                del displayed[key]
            continue
        for key, _, selector in group:
            selectors[key] = {"id": key, **selector}
        if len(displayed) == 16:
            break
    return payload(), selectors


def plan(cfg, model, missing):
    from .generation_run import Execution
    commit = source_commit(cfg, model)
    execution = Execution(cfg, None)
    path = cfg.build_dir / "first-run-plan.json"
    save(path, {"schema": 1, "source_commit": commit, "model_calls": 0,
                "pending": [_key(s, t) for s, t in missing], "execution": cfg.agent.label,
                "command": cfg.agent.command, "model": cfg.agent.model, "args": cfg.agent.args,
                "max_input_chars": cfg.agent.max_input_chars, "limits": execution.limits}, newline="\n")
    return path


def prepare(cfg, model, missing, execution):
    if cfg.agent.kind != "cli":
        raise ValueError("첫 실행 입력 자동 준비에는 설정한 문서 생성 CLI가 필요합니다.")
    from .validation_stage import stage
    from .matching import match_any
    commit = source_commit(cfg, model)
    locations = {file: rows for file, rows in _locations(model).items() if not match_any(file, cfg.exclude)}
    pairs = list(_scenario_pairs(model))
    fact_inputs, files = _fact_inputs(model.to_dict()), {}
    for sid, group in groupby(missing, key=lambda pair: pair[0]["id"]):
        topics = list(group)
        with execution.document(sid, [f"first_run_{s['id']}_{t['id']}" for s, t in topics]):
            for section, topic in topics:
                key = _key(section, topic)
                tag = f"first_run_{section['id']}_{topic['id']}"
                execution.unit(tag, "running")
                with stage() as inputs:
                    inputs.pin(cfg, model)
                    catalog = _catalog(cfg, commit, fact_inputs)
                    from .generated_visuals import plans
                    from .first_run_visual_budget import select
                    figures = [f for f in plans(cfg, section) if f["topic"] == topic["id"]]
                    pool = [({**entry, "candidate_id": f"window-{n}"}, source)
                            for n, (entry, source) in enumerate(islice(_candidates(
                                cfg, locations, files, commit, section, topic, pairs), 36), 1)]
                    request, selectors = _request(cfg, section, topic, pool, visual=bool(figures))
                    if not selectors:
                        raise ValueError(f"{key}: 입력 한도 안에서 사용할 소스 발췌 후보가 없습니다.")

                    def expand(previous, reason):
                        fresh = [pair for pair in pool if pair[0]["candidate_id"] not in previous]
                        names = {word.lower() for word in re.findall(r"[A-Za-z_][A-Za-z_0-9]{3,}", reason)}
                        fresh.sort(key=lambda pair: -sum(
                            word in pair[0]["text"].lower() for word in names))
                        prior = [pair for pair in pool if pair[0]["candidate_id"] in previous]
                        kept = prior[:3]
                        if len(prior) > 3 and "call_pair" in prior[2][0] and prior[2][0].get("call_pair") == prior[3][0].get("call_pair"):
                            kept.append(prior[3])
                        retry, choices = _request(cfg, section, topic, fresh[:2] + kept + fresh[2:],
                                                  visual=bool(figures), missing=reason)
                        return (retry, choices) if choices.keys() - previous.keys() else None

                    question, sources = select(cfg, model, files, section, topic, execution, request, selectors,
                                               tag, figures, expand=expand)
                    catalog["topics"][key] = {
                        "identity": _identity(cfg, section, topic), "question": question, "sources": sources,
                        "receipt": str(execution.last_receipt) if execution.last_receipt else None,
                    }
                    inputs.verify()
                    if source_commit(cfg, model) != commit:
                        raise ValueError("첫 실행 입력 준비 중 소스 커밋이 변경됐습니다.")
                save(catalog_path(cfg), catalog, newline="\n")
                execution.unit(tag, "completed")
    return catalog_path(cfg)
