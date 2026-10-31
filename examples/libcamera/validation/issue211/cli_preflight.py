"""Exercise exact issue-specific CLI profiles through the real loader/transport."""
import argparse
import json
from pathlib import Path

from sdd.config import load
from sdd.llm import Agent, AgentError
from sdd.cli_agent import arguments, command


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    results = {}
    for name in ('generation-profile', 'independent-review-profile'):
        config = load(Path(__file__).with_name(name + '.yaml')).agent
        agent = Agent(config, args.out / name)
        result = dict(argv=command(config) + arguments(config), status='incomplete')
        try:
            answer = agent.chat('Return only the requested short text. Do not use tools.',
                                'Return exactly: issue211 CLI preflight', tag='availability')
            result.update(status='completed', response=answer, receipt=str(agent.last_receipt))
        except AgentError as exc:
            result['error'] = str(exc)
        results[name] = result
        (args.out / 'results.json').write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
        print(name, result['status'], result.get('error', ''), flush=True)


if __name__ == '__main__':
    main()
