"""Conservative CI routing from complete Git trees, without a file-list API."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess


DOC_PARENTS = {'docs', 'docs/concepts', 'docs/reference', 'docs/records', 'docs/libcamera'}
POLICY = {'docs/concepts/site.md', 'docs/concepts/reader-quality.md',
          'docs/concepts/publication-inputs.md'}
SHA = re.compile(r'(?:[0-9a-f]{40}|[0-9a-f]{64})\Z')


def documentation(path):
    value = PurePosixPath(path)
    if (not path or value.as_posix() != path or value.is_absolute() or
            any(p in {'.', '..'} for p in value.parts) or
            any(ord(c) < 32 or c in '\\:' for c in path) or path in POLICY or
            value.name in {'AGENTS.md', 'CLAUDE.md', 'DESIGN.md'}):
        return False
    return path in {'README.md', 'ci/README.md'} or (
        value.suffix == '.md' and value.parent.as_posix() in DOC_PARENTS)


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.PIPE)


def entries(raw):
    """--no-renames represents both sides of a rename as independent paths."""
    chunks = raw.split(b'\0')
    if chunks.pop() != b'' or len(chunks) % 2:
        raise ValueError('Malformed Git raw diff')
    result = []
    for index in range(0, len(chunks), 2):
        fields = chunks[index].decode('ascii').split()
        if (len(fields) != 5 or not fields[0].startswith(':') or
                not SHA.fullmatch(fields[2]) or not SHA.fullmatch(fields[3])):
            raise ValueError('Malformed Git raw entry')
        result.append(dict(path=chunks[index+1].decode('utf-8'), old_mode=fields[0][1:],
                           new_mode=fields[1], status=fields[4]))
    return result


def classify(changes):
    if not changes:
        return 'full', 'empty-diff'
    for item in changes:
        if (item['status'] not in {'A', 'M', 'D'} or
                {item['old_mode'], item['new_mode']} - {'100644', '000000'} or
                not documentation(item['path'])):
            return 'full', 'runtime-policy-or-unknown-change'
    return 'docs', 'allowlisted-documentation-only'


def route(root, event_name, event, checkout):
    report = dict(schema=1, event=event_name, checkout=checkout, scope='full',
                  reason='explicit-or-unknown-event', base=None, head=None, changes=[])
    try:
        if not SHA.fullmatch(checkout):
            raise ValueError('Invalid checkout')
        actual = git(root, 'rev-parse', 'HEAD').decode().strip()
        if actual != checkout:
            raise ValueError('Checkout differs from event SHA')
        if event_name == 'pull_request':
            pr = event['pull_request']
            base, head = pr['base']['sha'], pr['head']['sha']
            if not all(isinstance(x, str) and SHA.fullmatch(x) for x in (base, head)):
                raise ValueError('Invalid pull request revisions')
            parents = git(root, 'show', '-s', '--format=%P', checkout).decode().split()
            if len(parents) != 2 or set(parents) != {base, head}:
                raise ValueError('Unverified pull request merge tree')
            # Inspect the entire tested merge tree against its actual base,
            # including additions, deletions, modes and both rename sides.
            report.update(base=base, head=checkout, pull_request_head=head)
        elif event_name == 'push' and event.get('ref') == 'refs/heads/main':
            base, head = event['before'], event['after']
            if head != checkout or not isinstance(base, str) or not SHA.fullmatch(base):
                raise ValueError('Invalid push revisions')
            report.update(base=base, head=head)
        else:
            return report  # Manual runs and release tags always exercise the full suite.
        raw = git(root, 'diff', '--raw', '-z', '--no-abbrev', '--no-renames',
                  '--no-ext-diff', '--no-textconv', report['base'], report['head'], '--')
        report['changes'] = entries(raw)
        report['scope'], report['reason'] = classify(report['changes'])
    except (KeyError, TypeError, ValueError, UnicodeError, OSError, subprocess.CalledProcessError):
        report.update(scope='full', reason='unavailable-or-unverified-history')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=Path('build/ci/scope.json'))
    args = parser.parse_args()
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text(encoding='utf-8'))
    result = route(Path.cwd(), os.environ['GITHUB_EVENT_NAME'], event, os.environ['GITHUB_SHA'])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=True, indent=2)+'\n', encoding='utf-8')
    if output := os.environ.get('GITHUB_OUTPUT'):
        with open(output, 'a', encoding='utf-8') as stream:
            stream.write('scope='+result['scope']+'\n')
    if summary := os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(summary, 'a', encoding='utf-8') as stream:
            stream.write(f"CI scope: **{result['scope']}**; reason: `{result['reason']}`; "
                         f"changed entries: {len(result['changes'])}.\n")
    print(json.dumps(result, ensure_ascii=True))


if __name__ == '__main__':
    main()
