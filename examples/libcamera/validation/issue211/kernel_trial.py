"""Prepare a reviewable temporary WSL kernel switch; apply only after approval.

This host currently has no .wslconfig. Refuse to overwrite any subsequently
created config. Restore refuses to erase concurrent changes. No modules are
installed, removed, or force-loaded. The caller must obtain issue #211's explicit
host-change approval before invoking apply or restore.
"""
import argparse
import json
from pathlib import Path
import sys

from sdd.runtime_evidence import run_recorded, sha256

ROOT = Path(__file__).resolve().parents[4]
EXPECTED = 'cf23bf492a00a5c7517e221b0d8f742ea3cffa9351823191a5ba5c476ba15460'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'apply', 'restore'))
    parser.add_argument('--trial', default='issue211-kernel-trial')
    args = parser.parse_args()
    if not args.trial.startswith('issue211-kernel-trial') or Path(args.trial).name != args.trial:
        raise ValueError('Trial records must stay inside this workspace')
    directory = ROOT / 'build' / args.trial
    config = Path.home() / '.wslconfig'
    kernel = ROOT / 'build/issue211-kernel/bzImage'
    if args.action == 'prepare':
        if config.exists():
            raise RuntimeError('Host state changed: .wslconfig exists; prepare a new reviewed proposal')
        if sha256(kernel) != EXPECTED:
            raise RuntimeError('Kernel hash mismatch')
        directory.mkdir(exist_ok=False)
        proposed = '[wsl2]\nkernel=' + str(kernel).replace('\\', '\\\\') + '\n'
        (directory / 'wslconfig.proposed').write_text(proposed, encoding='utf-8', newline='\n')
        state = dict(config=str(config), existed=False, original_kernel='6.18.33.2-microsoft-standard-WSL2',
                     kernel=str(kernel), kernel_sha256=EXPECTED,
                     proposed_sha256=sha256(directory / 'wslconfig.proposed'),
                     approval='required-before-apply',
                     impact='All WSL2 distributions share the test kernel. wsl --shutdown stops Ubuntu/Docker. '
                            'No matching modules are installed for the new release; keep Docker stopped during the trial. '
                            'The test kernel also reflects compiler capability changes captured in diffconfig. '
                            'Restore removes only the exact trial config and reboots to the packaged kernel.')
        (directory / 'proposal.json').write_text(json.dumps(state, indent=2) + '\n')
        print(json.dumps(state, indent=2))
        return
    state = json.loads((directory / 'proposal.json').read_text())
    proposed = (directory / 'wslconfig.proposed').read_bytes()
    if sha256(directory / 'wslconfig.proposed') != state['proposed_sha256']:
        raise RuntimeError('Proposal changed')
    if args.action == 'apply':
        if sha256(kernel) != EXPECTED:
            raise RuntimeError('Kernel changed')
        with config.open('xb') as stream:
            stream.write(proposed)
    else:
        if config.read_bytes() != proposed:
            raise RuntimeError('Concurrent WSL configuration change: refusing to erase it')
        config.unlink()
    record = run_recorded(directory / (args.action + '-shutdown'), ['wsl', '--shutdown'], timeout=60)
    if record['exit_code'] != 0 or record['timed_out']:
        raise RuntimeError('WSL shutdown incomplete; inspect preserved record and restore configuration')
    result = run_recorded(directory / (args.action + '-boot'),
                          ['wsl', '-d', 'Ubuntu', '--', 'uname', '-r'], timeout=60)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
