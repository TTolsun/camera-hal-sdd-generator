"""Build a deterministic, allowlisted import ZIP from a committed public revision."""
import argparse
import hashlib
import io
import json
import re
import subprocess
import tomllib
import zipfile
from pathlib import Path, PurePosixPath

ROOT_FILES = {"README.md", "DESIGN.md", "LICENSE", "pyproject.toml", "uv.lock", ".gitignore", ".gitattributes", "mkdocs.yml", "sdd.yaml"}
DIRECTORIES = {"src", "docs", "skills", "style", "templates", "prompts", "examples", "config", "tests", "ci", "tools"}
PREFIX = "camera-hal-sdd-generator/"


def start_prompts(guide):
    """Keep release attachments and the offline kit on the same instructions."""
    guide = guide.replace("\r\n", "\n")
    sections = re.findall(r"^## 시작 프롬프트\n(.*?)(?=^## |\Z)", guide, re.M | re.S)
    if len(sections) != 1:
        raise ValueError("Expected one start prompt section in docs/inhouse/package.md")
    blocks = re.findall(r"^```text\n(.*?)^```[ \t]*$", sections[0], re.M | re.S)
    if len(blocks) != 1 or not blocks[0].strip():
        raise ValueError("Expected one nonempty text block in start prompt section")
    prompt = blocks[0].rstrip() + "\n"
    selection = "문서 생성·번역 CLI: <hermes | opencode | claude | codex; 기존 사내 설정을 유지하려면 명시>"
    if prompt.count(selection) != 1:
        raise ValueError("Expected one CLI selection in start prompt")
    hermes = prompt.replace(selection, "문서 생성·번역 CLI: hermes (승인된 기존 Hermes 모델·제공자 설정을 유지)")
    return {"START_PROMPT.txt": prompt.encode(), "START_PROMPT_HERMES.txt": hermes.encode()}


def selected(name):
    parts = PurePosixPath(name).parts
    if name.startswith("examples/libcamera/validation/") and len(parts) > 5:
        return False  # historical raw model responses/prompts are not onboarding inputs
    return (name in ROOT_FILES or len(parts) > 1 and parts[0] in DIRECTORIES) and not any(
        part in {".git", ".venv", "__pycache__", "build", "site", "sdd.local.yaml", ".env", "CLAUDE.md", "AGENTS.md"}
        or part.endswith((".pyc", ".local.yaml")) for part in parts)


def requirements(lock):
    packages = {p["name"]: p for p in tomllib.loads(lock.decode())["package"]}
    root = packages["camera-hal-sdd-generator"]
    todo = [d["name"] for d in root["dependencies"] + root.get("optional-dependencies", {}).get("dev", [])]
    seen = set()
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        todo.extend(d["name"] for d in packages[name].get("dependencies", []))
    # Include conditional runtime/dev dependencies on all targets; pip still checks
    # wheel compatibility. Do not bundle host-specific virtual environments.
    return ("# Runtime and test dependencies pinned from the included uv.lock.\n" +
            "\n".join(f"{n}=={packages[n]['version']}" for n in sorted(seen)) + "\n").encode()


def build(repo, output, ref="HEAD"):
    repo, output = Path(repo).resolve(), Path(output).resolve()
    revision = subprocess.check_output(["git", "-C", str(repo), "rev-parse", f"{ref}^{{commit}}"], text=True).strip()
    archive = subprocess.check_output(["git", "-C", str(repo), "archive", "--format=zip", revision])
    files = {}
    with zipfile.ZipFile(io.BytesIO(archive)) as source:
        for entry in source.infolist():
            if not entry.is_dir() and selected(entry.filename):
                if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError(f"Symlinks are not import payloads: {entry.filename}")
                files[entry.filename] = source.read(entry)
    required = {"docs/inhouse/package.md", "docs/inhouse/import-agent.md", "skills/camera-hal-sdd/SKILL.md",
                "examples/inhouse-template/sdd.yaml", "examples/inhouse-template/config/visuals.yaml",
                "src/sdd/generated_visuals.py", "tools/evaluate_visuals.py",
                "src/sdd/evaluate_pipeline.py", "src/sdd/provenance.py", "src/sdd/design_replay.py",
                "src/sdd/cli.py", "tools/verify_import.py", "tools/run_sdd.py", "uv.lock"}
    if missing := required - files.keys():
        raise ValueError(f"Missing committed package inputs: {sorted(missing)}")
    files["AGENTS.md"] = files.pop("docs/inhouse/import-agent.md")
    files.update(start_prompts(files["docs/inhouse/package.md"].decode("utf-8")))
    files["START_HERE.md"] = ("# 사내 에이전트 반입 패키지\n\n"
        "**[시작 안내](docs/inhouse/package.md)를 여세요.** 시작 프롬프트, 실행 순서, 합격 기준, 복구 절차가 한 곳에 있습니다.\n\n"
        "먼저 `python tools/verify_import.py`로 반입 파일을 검증하세요. 의존성과 제품 툴체인은 별도 준비합니다.\n\n"
        "검증 후 `START_PROMPT.txt`의 경로와 승인 설정을 채워 에이전트에게 전달하세요. "
        "Hermes를 선택했다면 `START_PROMPT_HERMES.txt`를 사용합니다. 두 파일은 같은 시작 안내에서 생성됩니다.\n").encode()
    files["requirements-inhouse.txt"] = requirements(files["uv.lock"])
    manifest = {"schema": 1, "source_commit": revision, "entry": "START_HERE.md",
                "scope": "Public generator source, guides, skill and templates; no internal inputs or execution outputs.",
                "excluded": ["Git history/remotes", "local configuration", "generated documents/facts/logs", "historical raw model responses/prompts", "public deployment agent instructions", "Python wheels", "product toolchain", "Mermaid distribution"],
                "generated": {"AGENTS.md": "docs/inhouse/import-agent.md", "START_HERE.md": "tools/build_inhouse_package.py",
                              "START_PROMPT.txt": "docs/inhouse/package.md#시작-프롬프트",
                              "START_PROMPT_HERMES.txt": "docs/inhouse/package.md#시작-프롬프트 (Hermes selection)",
                              "requirements-inhouse.txt": "uv.lock runtime/dev dependency closure"},
                "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}}
    files["IMPORT-MANIFEST.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() or output.with_suffix(output.suffix + ".sha256").exists():
        raise ValueError(f"Output already exists: {output}")
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as target:
        for name, data in sorted(files.items()):
            entry = zipfile.ZipInfo(PREFIX + name, (2020, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            target.writestr(entry, data)
    checksum = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix + ".sha256").write_text(f"{checksum}  {output.name}\n", encoding="utf-8", newline="\n")
    return {"zip": str(output), "sha256": checksum, "source_commit": revision, "payload_files": len(manifest["files"])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--ref", default="HEAD", help="Committed revision only; working tree changes are not packaged")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.repo, args.out, args.ref), ensure_ascii=False))


if __name__ == "__main__":
    main()
