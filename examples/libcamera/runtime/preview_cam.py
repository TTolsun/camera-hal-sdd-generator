"""Print planned arguments without executing cam or changing the host."""
import argparse
import json
import sys
sys.dont_write_bytecode = True
from cam_invocation import capture_argv
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(dict(schema=1, kind='invocation-plan', executed=False,
                          cam_argv=capture_argv(args.build.resolve() / 'src/apps/cam/cam')),
                     indent=2))


if __name__ == '__main__':
    main()
