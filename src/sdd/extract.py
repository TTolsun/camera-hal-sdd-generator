"""사실 추출 오케스트레이션: compile DB -> (clang-uml | libclang callgraph) -> libclang 주석 -> flags -> facts.json"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from . import compdb
from .config import Config
from .facts import callgraph, clang_uml, comments, docblocks, flags
from .facts.model import KnowledgeModel


def git_head(repo: Path) -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True,
                              capture_output=True, text=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def structure_backend(cfg: Config) -> str:
    """'clang-uml' 이 PATH 에 있으면 그것을, 없거나 tools.clang_uml 이 none 이면 libclang 대체 경로를 쓴다."""
    if cfg.clang_uml_bin.lower() in ("none", "off", ""):
        return "libclang"
    return "clang-uml" if shutil.which(cfg.clang_uml_bin) else "libclang"


def run(cfg: Config, skip_comments: bool = False, skip_clang_uml: bool = False,
        only_diagrams: list[str] | None = None) -> KnowledgeModel:
    compdb_path = compdb.ensure(cfg)
    entries = compdb.load_entries(compdb_path)
    if not entries:
        raise RuntimeError("compile DB가 비어 있습니다. 실제 빌드 구성을 확인한 뒤 다시 추출하세요.")
    for w in compdb.check(entries):
        print(f"[compdb] 경고: {w}")

    backend = "none" if skip_clang_uml else structure_backend(cfg)
    model = KnowledgeModel(meta={
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source_root": cfg.source_root.as_posix(),
        "source_commit": git_head(cfg.source_root),
        "compile_commands": compdb_path.as_posix(),
        "translation_units": len(entries),
        "build_config": "ndk-build" if cfg.ndk_build.get("enabled") else "simple_compdb",
        "structure_backend": backend,
    })

    if backend == "clang-uml":
        cfg_path = clang_uml.write_config(cfg, compdb_path.parent)
        diagrams_dir = clang_uml.run(cfg, cfg_path, only=only_diagrams)
        clang_uml.parse_into(model, cfg, diagrams_dir)
        _copy_mermaid(diagrams_dir, cfg.diagrams_dir, _roots(cfg))

    # 주석과 선언/정의 위치는 항상 libclang 이 채운다. clang-uml 이 없을 때는 클래스 목록 자체도 여기서 나온다.
    if not skip_comments or backend == "libclang":
        stats = comments.collect(model, cfg, entries)
        model.meta["comments"] = stats
        print(f"[comments] TU {stats['tus']} 개, 파싱 오류 {stats['errors']} 개, "
              f"클래스 {stats['classes']}, 메서드 {stats['methods']}, 함수 {stats['functions']}")
        if stats["errors"]:
            raise RuntimeError(f"Clang 파싱 오류 {stats['errors']}개로 추출을 중단합니다. "
                               "compile DB의 include 경로, 매크로와 생성 헤더를 확인하세요. 기존 facts는 보존합니다.")

    # 선언에 붙지 않은 문서 주석은 libclang 이 어디에도 주지 않는다. 클래스 설명이 구현 파일에
    # 따로 적혀 있는 코드베이스에서는 이 단계가 없으면 설명이 통째로 빠진다.
    doc = docblocks.collect(model, cfg, entries)
    print(f"[docblocks] 문서 주석 블록 {doc['blocks']} 개에서 설명 {doc['filled']} 개를 채웠습니다. "
          f"이름이 모호해 건너뜀 {doc['ambiguous']} 개, 사실에 없는 이름 {doc['unknown']} 개")
    model.meta["docblocks"] = doc

    if backend == "libclang":
        stats = callgraph.collect(model, cfg, entries)
        print(f"[callgraph] clang-uml 없이 libclang 으로 추적: 함수 정의 {stats['functions']} 개, "
              f"시나리오 {stats['scenarios']} 개, 진입점 못 찾음 {stats['missing_entries']} 개")
        if stats["missing_entries"]:
            raise RuntimeError(f"시나리오 진입점 {stats['missing_entries']}개를 찾지 못했습니다. "
                               "scenarios.yaml을 실제 정의와 대조하세요. 기존 facts는 보존합니다.")

    model.meta["compile_units"] = _compile_units(cfg, entries, model.meta.get("parsed_files"),
                                                 str(model.meta.get("source_commit", "")))
    flags.collect(model, cfg, entries)
    from .evidence import collect as collect_evidence
    collect_evidence(cfg, model)

    model = KnowledgeModel.from_dict(comments.portable_names(model.to_dict(), _roots(cfg)))
    model.meta["classes"] = len(model.classes)
    model.meta["functions"] = len(model.functions)
    model.meta["scenarios"] = len(model.scenarios)
    model.meta["defines"] = len(model.defines)
    model.save(cfg.facts_path)
    return model


def _compile_units(cfg: Config, entries: list[dict], parsed: list[str] | None,
                   commit: str = "") -> dict[str, str]:
    """분석한 빌드의 지문: TU 별 컴파일 인자, 그리고 Git 이 추적하지 않는(빌드가 만든) 헤더의 내용.

    빌드 파일 변경이 문서에 주는 영향은 이 지문의 변화로 모두 드러난다. 범위 검사가 이전 facts 와 비교한다.
    - 커밋 ID 와 describe 거리(-DVERSION="0.7.2+178-dfc7c9a4")는 가린다. Meson 처럼 다시 구성할 때만 값을
      정하는 빌드는 예전 커밋의 ID 를 그대로 두므로, 추출한 커밋뿐 아니라 이 저장소의 어떤 커밋 ID 든 가린다.
    - 빌드가 만든 소스 파일(TU)의 내용은 비교하지 않는다. 다른 TU 에 포함되지 않으므로 다른 파일의 동작을
      바꾸지 않고, 버전·빌드 시각 문자열 때문에 커밋마다 달라진다. 그 TU 의 컴파일 인자는 비교한다.
    """
    roots = _roots(cfg)
    argvs: list[tuple[str, str]] = []
    for entry, path in zip(entries, compdb.translation_units(entries)):
        rel = comments.root_relative(str(path), roots)
        if rel:
            argvs.append((rel, json.dumps(compdb._argv(entry), ensure_ascii=False)))
    commits = _commit_ids(cfg, [a for _, a in argvs], commit)
    units: dict[str, list[str]] = {}
    for rel, argv in argvs:
        argv = _without_commit_id(argv, commits)
        units.setdefault(rel, []).append(hashlib.sha256(argv.encode("utf-8")).hexdigest())
    out = {rel: hashlib.sha256("\n".join(sorted(h)).encode()).hexdigest()[:16] for rel, h in units.items()}
    try:
        tracked = set(subprocess.run(["git", "ls-files", "-z"], cwd=cfg.source_root, capture_output=True,
                                     check=True).stdout.decode("utf-8", "replace").split("\0"))
    except (OSError, subprocess.CalledProcessError):
        return out
    for rel in parsed or []:
        if rel not in tracked and rel not in units:
            try:
                text = (cfg.source_root / rel).read_bytes().decode("utf-8", "replace")
            except OSError:
                continue
            text = _without_commit_id(text, commits | _commit_ids(cfg, [text], commit))
            out[f"generated:{rel}"] = hashlib.sha256(text.encode()).hexdigest()[:16]
    return out


_HEX = re.compile(r"[0-9a-f]{7,40}")


def _commit_ids(cfg: Config, texts: list[str], commit: str = "") -> set[str]:
    """texts 안의 7~40자 16진 문자열 가운데 이 저장소의 커밋을 가리키는 것."""
    candidates = sorted({m.group(0) for t in texts for m in _HEX.finditer(t)})
    found = {c for c in candidates if commit and commit.startswith(c)}
    rest = [c for c in candidates if c not in found]
    if not rest:
        return found
    try:
        res = subprocess.run(["git", "cat-file", "--batch-check"], cwd=cfg.source_root, input="\n".join(rest) + "\n",
                             capture_output=True, encoding="utf-8", check=True)
    except (OSError, subprocess.CalledProcessError):
        return found
    for token, line in zip(rest, res.stdout.splitlines()):
        if line.split()[1:2] == ["commit"]:
            found.add(token)
    return found


def _without_commit_id(text: str, commits: set[str]) -> str:
    """커밋 ID 와 그 앞의 describe 거리를 고정 문자열로 바꾼다."""
    if not commits:
        return text
    text = _HEX.sub(lambda m: "<commit>" if m.group(0) in commits else m.group(0), text)
    return re.sub(r"\d+-g?<commit>", "N-<commit>", text)


def _roots(cfg: Config) -> tuple[str, ...]:
    return (os.path.abspath(cfg.source_root), str(cfg.source_root.resolve()))


def _copy_mermaid(src: Path, dst: Path, roots: tuple[str, ...]) -> None:
    # clang-uml 그림에도 이름 없는 형식의 절대 경로가 들어 있으므로 facts 와 같은 규칙으로 바꾼다.
    dst.mkdir(parents=True, exist_ok=True)
    for f in src.glob("*.mmd"):
        text = comments.portable_names(f.read_text(encoding="utf-8"), roots)
        (dst / f.name).write_text(text, encoding="utf-8", newline="\n")
