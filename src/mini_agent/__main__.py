"""CLI entry point: mini-agent <prompt> or echo <prompt> | mini-agent"""

import sys

from mini_agent.agent_loop import run_sync as run


def main() -> None:
    user_input = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else sys.stdin.read().strip()
    if not user_input:
        print("Usage: mini-agent <prompt>", file=sys.stderr)
        sys.exit(1)
    print(run(user_input))


if __name__ == "__main__":
    main()
