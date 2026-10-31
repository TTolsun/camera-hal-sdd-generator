"""Create a new evidence directory; inventory never edits shared WSL state."""
import argparse
import json
from pathlib import Path
import subprocess

from sdd.runtime_evidence import run_recorded
from sdd.config import load
from sdd.cli_agent import arguments, command


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[4]
    linux_root = '/mnt/' + root.drive[0].lower() + root.as_posix()[2:]
    commands = {
        'git-status': ['git', 'status', '--short'],
        'wsl-list': ['wsl', '--list', '--verbose'],
        'wsl-version': ['wsl', '--version'],
        'wsl-inventory': ['wsl', '-d', 'Ubuntu', '--', 'bash', linux_root + '/examples/libcamera/runtime/inspect_wsl.sh'],
        'claude-help': ['claude', '--help'],
        'claude-version': ['claude', '--version'],
        'codex-help': ['codex', 'exec', '--help'],
        'codex-version': ['codex', '--version'],
    }
    for name, argv in commands.items():
        result = run_recorded(args.out / name, argv, timeout=60)
        print(name, result['exit_code'], result['timed_out'], flush=True)
    profiles = {}
    for name in ('generation-profile', 'independent-review-profile'):
        config = load(Path(__file__).with_name(name + '.yaml')).agent
        profiles[name] = dict(kind=config.kind, runner=config.runner, model=config.model,
                              argv=command(config) + arguments(config))
    (args.out / 'loaded-profiles.json').write_text(json.dumps(profiles, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
