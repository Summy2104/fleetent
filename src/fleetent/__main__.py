"""CLI entry point.

- ``fleetent agent init <agent-id> [--home PATH] [--force]``: scaffold a runnable agent
  home (``agent.yaml`` + ``.env``) from a built-in template; no platform/DB.
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
    parser.add_argument("agent_id", help="agent id (home at FLEETENT_HOME/agents/<agent-id>/)")
    parser.add_argument("--port", type=int, default=None, help="serve HTTP /chat + /ws on PORT")
    parser.add_argument("--home", default=None, help="override the agent home directory")
    return parser.parse_args(args)


def _parse_agent_init(args: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="fleetent agent init")
    parser.add_argument("agent_id", help="agent id (home at FLEETENT_HOME/agents/<agent-id>/)")
    parser.add_argument("--home", default=None, help="override the agent home directory")
    parser.add_argument("--force", action="store_true", help="overwrite an existing agent.yaml")
    return parser.parse_args(args)


def main() -> None:
    argv = sys.argv[1:]
    if argv[:2] == ["agent", "init"]:
        from fleetent.runtime import agent_init

        ns = _parse_agent_init(argv[2:])
        home = agent_init.scaffold_agent_home(ns.agent_id, home=ns.home, force=ns.force)
        print(f"Scaffolded agent home: {home}")
        print(f"  next: edit {home}/agent.yaml + {home}/.env")
        print(f"  then: fleetent agent run {ns.agent_id}")
        return

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
