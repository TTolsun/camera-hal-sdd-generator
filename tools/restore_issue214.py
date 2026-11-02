"""Restore the public PR69 evidence without modifying its receipts or verdicts."""
from pathlib import Path
import hashlib
import json
import tarfile
import zipfile
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT/'build/issue214'
FIXTURE = WORK/'fixture'
BASELINE = WORK/'baseline'


def extract_zip(archive, target, select=lambda name: True):
    with zipfile.ZipFile(archive) as source:
        for item in source.infolist():
            if not select(item.filename) or item.is_dir():
                continue
            path = (target/item.filename).resolve()
            if not path.is_relative_to(target.resolve()):
                raise ValueError('Unsafe archive member')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(source.read(item))


def main():
    BASELINE.mkdir(parents=True, exist_ok=True)
    with tarfile.open(WORK/'baseline.tar') as archive:
        archive.extractall(BASELINE, filter='data')
    extract_zip(WORK/'archives/base.zip', FIXTURE/'base',
                lambda n: n.startswith('latest293/config/') or n.startswith('latest293/run/'))
    extract_zip(WORK/'archives/followup.zip', FIXTURE)
    old = 'C:\\Users\\baboe\\.codex\\worktrees\\ba65\\camera-hal-sdd-generator'

    def relocate(value):
        if isinstance(value, dict):
            return {key: relocate(val) for key, val in value.items()}
        if isinstance(value, list):
            return [relocate(val) for val in value]
        if not isinstance(value, str) or not value.startswith(old):
            return value
        tail = value[len(old):].replace('\\', '/').lstrip('/')
        for prefix in ('build/issue193/queue-return/', 'build/issue193/comment-followup/'):
            if tail.startswith(prefix):
                return str(FIXTURE/tail[len(prefix):])
        if tail.startswith('build/issue193/latest293/'):
            return str(FIXTURE/'base/latest293'/tail[len('build/issue193/latest293/'):])
        return str(BASELINE/tail)

    for name in ('publication.yaml', 'independent-review.yaml'):
        data = yaml.safe_load((FIXTURE/name).read_bytes())
        data = relocate(data)
        (FIXTURE/name).write_text(yaml.safe_dump(data, allow_unicode=True), encoding='utf-8')
    manifest = {str(p.relative_to(WORK)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(FIXTURE.rglob('*')) if p.is_file()}
    (WORK/'restored-inputs.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(f'Restored {len(manifest)} files; original receipt bytes preserved.', flush=True)


if __name__ == '__main__':
    main()
