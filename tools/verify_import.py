"""Verify the untouched import payload using Python's standard library only."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath


def verify(root):
    root = Path(root).resolve()
    manifest = json.loads((root / "IMPORT-MANIFEST.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != 1 or not isinstance(manifest.get("files"), dict) or not manifest["files"]:
        raise ValueError("Invalid import manifest")
    failures = []
    for name, expected in manifest["files"].items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts or "\\" in name or ":" in name:
            raise ValueError(f"Unsafe manifest path: {name}")
        path = root.joinpath(*relative.parts)
        if not path.resolve().is_relative_to(root) or path.is_symlink():
            raise ValueError(f"Path escapes the import: {name}")
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            failures.append(name)
    # Verify before installing dependencies or creating project outputs in this root.
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    extra = actual - set(manifest["files"]) - {"IMPORT-MANIFEST.json"}
    if failures or extra:
        raise ValueError(f"Import differs: missing/changed={sorted(failures)}, unexpected={sorted(extra)}")
    return {"source_commit": manifest["source_commit"], "verified_files": len(manifest["files"])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.root), ensure_ascii=False))
        return 0
    except (OSError, ValueError) as exc:
        print(f"Import verification failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
