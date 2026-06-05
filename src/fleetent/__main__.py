"""CLI entry point.

- ``fleetent agent run <agent-id> [--port N] [--home PATH]``: run one agent as a
  self-contained foreground process (loop + bound IM, optional HTTP/ws).
- ``fleetent "<prompt>"`` (or piped stdin): one-shot run as the deployed home agent.
"""

import argparse
import asyncio
import sys

from fleetent.runtime import run_sync as run


def _parse_agent_run(args: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="fleetent agent run")
    parser.add_argument("agent_id", help="agent id (home at FLEETENT_HOME/<agent-id>/)")
    parser.add_argument("--port", type=int, default=None, help="serve HTTP /chat + /ws on PORT")
    parser.add_argument("--home", default=None, help="override the agent home directory")
    return parser.parse_args(args)


def main() -> None:
    argv = sys.argv[1:]
    if argv[:2] == ["agent", "run"]:
        from fleetent.runtime import agent_app

        ns = _parse_agent_run(argv[2:])
        asyncio.run(agent_app.serve(ns.agent_id, port=ns.port, home=ns.home))
        return

    user_input = " ".join(argv) if argv else sys.stdin.read().strip()
    if not user_input:
        print(
            "Usage: fleetent <prompt>  |  fleetent agent run <agent-id> [--port N]",
            file=sys.stderr,
        )
        sys.exit(1)
    print(run(user_input))


if __name__ == "__main__":
    main()
