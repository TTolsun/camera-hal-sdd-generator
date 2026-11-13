"""Run the archived public SDD reader with separate document and source tools."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from sdd.cli_agent import arguments, command, run
from sdd.config import AgentConfig


ROUTE_OUTPUT_TOKEN_LIMIT = 65_536
SPLIT_READER = Path(__file__).with_name('split_reader.py')


def reader_options(reader: Path, site: Path, navigation: Path, *,
                   output_token_limit: int = ROUTE_OUTPUT_TOKEN_LIMIT,
                   combined_route: bool = False) -> list[str]:
    """Scope the output budget to the reader tools for this run."""
    if type(output_token_limit) is not int or output_token_limit < 1:
        raise ValueError('Route output token limit must be a positive integer')
    args = [str(path.resolve()) for path in (reader, site, navigation)]
    tools = ['route']
    if not combined_route:
        args.insert(0, str(SPLIT_READER.resolve()))
        tools.append('route_source')
    settings = {
        'command': sys.executable,
        'args': args,
        'required': True,
        'default_tools_approval_mode': 'approve',
        'startup_timeout_sec': 75,
        'tool_timeout_sec': 85,
        'enabled_tools': tools,
    }
    settings.update({f'tools.{tool}.output_token_limit': output_token_limit for tool in tools})
    return [part for key, value in settings.items()
            for part in ('-c', f'mcp_servers.public_sdd.{key}={json.dumps(value)}')]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reader', type=Path, required=True, help='Archived reader.py')
    parser.add_argument('--site', type=Path, required=True, help='Verified public site snapshot')
    parser.add_argument('--prompt', type=Path, required=True,
                        help='Prompt using route for documents and following its cursor through route_source')
    parser.add_argument('--out', type=Path, required=True, help='New directory for native output')
    parser.add_argument('--output-token-limit', type=int, default=ROUTE_OUTPUT_TOKEN_LIMIT)
    parser.add_argument('--combined-route', action='store_true',
                        help='Replay an archived prompt with the original single-response tool')
    args = parser.parse_args(argv)

    prompt = args.prompt.read_text(encoding='utf-8-sig')
    profile = AgentConfig(kind='cli', runner='codex', model='gpt-6.1-terra',
                          args=['-c', 'model_reasoning_effort="high"'], timeout_sec=360)
    options = reader_options(args.reader, args.site, args.out / 'navigation.jsonl',
                             output_token_limit=args.output_token_limit, combined_route=args.combined_route)
    args.out.mkdir(parents=True)
    invocation = [*command(profile), *arguments(profile), *options, '-']
    try:
        result = run(invocation, cwd=args.out.resolve(), prompt=prompt, timeout=profile.timeout_sec)
    except RuntimeError as error:
        for name in ('stdout', 'stderr'):
            output = getattr(error, name, '')
            if isinstance(output, str):
                output = output.encode()
            (args.out / (name + ('.jsonl' if name == 'stdout' else '.log'))).write_bytes(output)
        raise
    (args.out / 'stdout.jsonl').write_text(result.stdout, encoding='utf-8')
    (args.out / 'stderr.log').write_text(result.stderr, encoding='utf-8')
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
