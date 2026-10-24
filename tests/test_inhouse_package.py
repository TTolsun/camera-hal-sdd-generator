"""The transferable kit must be reproducible, isolated, verifiable and executable."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


builder = module("build_inhouse_package")
verifier = module("verify_import")


@pytest.fixture
def kit_repo(tmp_path):
    repo = tmp_path / "source repo"
    repo.mkdir()
    files = {
        "docs/inhouse/package.md": "Start here.",
        "docs/inhouse/import-agent.md": "Internal destinations only.",
        "skills/camera-hal-sdd/SKILL.md": "Skill.",
        "examples/inhouse-template/sdd.yaml": "agent: {kind: dry-run}",
        "src/sdd/__init__.py": "",
        "src/sdd/cli.py": "import sys\ndef main(): return 7 if '--fail' in sys.argv else 0\n",
        "AGENTS.md": "PUBLIC DEPLOYMENT INSTRUCTION MUST NOT TRAVEL",
        "CLAUDE.md": "PUBLIC DEPLOYMENT INSTRUCTION MUST NOT TRAVEL",
        "build/facts.json": "PRIVATE OUTPUT",
        "examples/inhouse-template/sdd.local.yaml": "SECRET",
        "examples/inhouse-template/.env": "SECRET",
        "sdd/generated.md": "GENERATED OUTPUT",
        "examples/libcamera/validation/run/model/repeat/response.md": "HISTORICAL RAW",
        "examples/libcamera/validation/run/result.json": "{}",
    }
    for tool in ("verify_import.py", "run_sdd.py"):
        files[f"tools/{tool}"] = (ROOT / "tools" / tool).read_text(encoding="utf-8")
    files["uv.lock"] = (ROOT / "uv.lock").read_text(encoding="utf-8")
    for name, text in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                    "commit", "-qm", "fixture"], check=True)
    # An uncommitted file under an allowed directory must not enter the kit.
    (repo / "docs/private-notes.md").write_text("PRIVATE UNTRACKED", encoding="utf-8")
    return repo


def test_package_is_committed_allowlisted_deterministic_and_relocatable(kit_repo, tmp_path):
    first, second = tmp_path / "one.zip", tmp_path / "two.zip"
    info = builder.build(kit_repo, first)
    assert builder.build(kit_repo, second)["sha256"] == info["sha256"]
    assert first.read_bytes() == second.read_bytes()
    moved = tmp_path / "moved import with spaces"
    with zipfile.ZipFile(first) as archive:
        names = archive.namelist()
        assert all(n.startswith(builder.PREFIX) for n in names)
        assert not any("private-notes" in n or "sdd.local" in n or "/.env" in n or "/build/" in n or "CLAUDE.md" in n or "response.md" in n for n in names)
        archive.extractall(moved)
    root = moved / "camera-hal-sdd-generator"
    assert (root / "AGENTS.md").read_text() == "Internal destinations only."
    assert not (root / ".git").exists()
    assert verifier.verify(root)["source_commit"] == info["source_commit"]
    result = subprocess.run([sys.executable, str(root / "tools/verify_import.py")], cwd=tmp_path, capture_output=True)
    assert result.returncode == 0, result.stdout
    # Run outside the package, without installing it, and retain a failed CLI exit.
    result = subprocess.run([sys.executable, str(root / "tools/run_sdd.py"), "--fail"], cwd=tmp_path, capture_output=True)
    assert result.returncode == 7, result.stderr
    with pytest.raises(ValueError, match="already exists"):
        builder.build(kit_repo, first)


def test_import_rejects_modified_missing_and_added_files_then_recovers(kit_repo, tmp_path):
    archive = tmp_path / "kit.zip"
    builder.build(kit_repo, archive)
    with zipfile.ZipFile(archive) as source:
        source.extractall(tmp_path / "unpacked")
    root = tmp_path / "unpacked/camera-hal-sdd-generator"
    target = root / "examples/inhouse-template/sdd.yaml"
    original = target.read_bytes()
    target.write_bytes(b"changed")
    with pytest.raises(ValueError, match="missing/changed"):
        verifier.verify(root)
    target.unlink()
    with pytest.raises(ValueError, match="missing/changed"):
        verifier.verify(root)
    target.write_bytes(original)
    added = root / "unexpected.txt"
    added.write_text("unexpected")
    with pytest.raises(ValueError, match="unexpected"):
        verifier.verify(root)
    added.unlink()
    assert verifier.verify(root)["verified_files"] > 0
    manifest = json.loads((root / "IMPORT-MANIFEST.json").read_text(encoding="utf-8"))
    manifest["files"]["../outside"] = "0" * 64
    (root / "IMPORT-MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="Unsafe"):
        verifier.verify(root)


def test_dependency_list_contains_locked_runtime_and_test_closure():
    lines = builder.requirements((ROOT / "uv.lock").read_bytes()).decode().splitlines()
    pins = {line.split("==")[0] for line in lines if not line.startswith("#")}
    assert {"libclang", "markdown", "pymdown-extensions", "pyyaml", "tzdata", "pytest", "pluggy", "packaging"} <= pins
    assert "mkdocs-material" not in pins
    assert not any("http" in line or line.startswith("-e") for line in lines)
