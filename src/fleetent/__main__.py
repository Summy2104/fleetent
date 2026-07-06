"""CLI entry point.

- ``fleetent agent init <agent-id> [--home PATH] [--force]``: scaffold a runnable agent
  home (``agent.yaml`` + ``.env``) from a built-in template for node-launched agents
  and local dev/test; no platform/DB.
- ``fleetent agent run <agent-id> [--port N] [--home PATH]``: run one agent as a
  foreground process (loop + bound IM, optional HTTP/ws) used by node and local dev/test.
- ``fleetent agent restart <agent-id> [--port N] [--home PATH]``: gracefully stop the
  running agent (SIGUSR1 drain → SIGTERM → SIGKILL) then boot a fresh one.
- ``fleetent "<prompt>"`` (or piped stdin): one-shot run as the deployed home agent.
"""

import argparse
import asyncio
import sys

from fleetent.runtime import run_sync as run


def _parse_agent_run(args: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="fleetent agent run")
    parser.add_argument(
        "agent_id",
        help="agent id (home at FLEETENT_HOME/tenants/default/agents/<agent-id>/)",
    )
    parser.add_argument("--port", type=int, default=None, help="serve HTTP /chat + /ws on PORT")
    parser.add_argument("--home", default=None, help="override the agent home directory")
    parser.add_argument("--no-im", action="store_true", help="disable in-process IM supervisors")
    return parser.parse_args(args)


def _parse_agent_restart(args: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="fleetent agent restart")
    parser.add_argument(
        "agent_id",
        help="agent id (home at FLEETENT_HOME/tenants/default/agents/<agent-id>/)",
    )
    parser.add_argument("--port", type=int, default=None, help="serve HTTP /chat + /ws on PORT")
    parser.add_argument("--home", default=None, help="override the agent home directory")
    parser.add_argument("--no-im", action="store_true", help="disable in-process IM supervisors")
    return parser.parse_args(args)


def _parse_agent_stop(args: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="fleetent agent stop")
    parser.add_argument(
        "agent_id",
        help="agent id (home at FLEETENT_HOME/tenants/default/agents/<agent-id>/)",
    )
    parser.add_argument("--home", default=None, help="override the agent home directory")
    return parser.parse_args(args)


def _parse_agent_init(args: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="fleetent agent init")
    parser.add_argument(
        "agent_id",
        help="agent id (home at FLEETENT_HOME/tenants/default/agents/<agent-id>/)",
    )
    parser.add_argument("--home", default=None, help="override the agent home directory")
    parser.add_argument("--force", action="store_true", help="overwrite an existing agent.yaml")
    return parser.parse_args(args)


def main(argv: list[str] | None = None) -> None:
    if argv is None:
        argv = sys.argv[1:]
    if argv[:1] == ["version"]:
        from fleetent.build_info import build_commit

        print(build_commit())
        return

    if argv[:2] == ["agent", "init"]:
        from fleetent.runtime import agent_init

        ns = _parse_agent_init(argv[2:])
        home = agent_init.scaffold_agent_home(ns.agent_id, home=ns.home, force=ns.force)
        print(f"Scaffolded agent home: {home}")
        print(f"  next: edit {home}/agent.yaml + {home}/.env")
        print(f"  then: fleetent agent run {ns.agent_id}")
        return

    if argv[:2] == ["agent", "run"]:
        from fleetent.build_info import log_service_startup
        from fleetent.runtime import agent_app

        ns = _parse_agent_run(argv[2:])
        log_service_startup("agent")
        asyncio.run(agent_app.serve(ns.agent_id, port=ns.port, home=ns.home, start_im=not ns.no_im))
        return

    if argv[:2] == ["agent", "restart"]:
        from fleetent.runtime import agent_app

        ns = _parse_agent_restart(argv[2:])
        home_dir = agent_app.resolve_home(ns.agent_id, ns.home)
        agent_app._stop_running(home_dir)
        asyncio.run(agent_app.serve(ns.agent_id, port=ns.port, home=ns.home, start_im=not ns.no_im))
        return

    if argv[:2] == ["agent", "stop"]:
        from fleetent.runtime import agent_app

        ns = _parse_agent_stop(argv[2:])
        home_dir = agent_app.resolve_home(ns.agent_id, ns.home)
        agent_app._stop_running(home_dir)
        return

    if argv and argv[0] == "platform":
        from fleetent.platform.platform_cli.main import main as platform_main

        platform_main(argv[1:], prog="fleetent platform")
        return

    if argv and argv[0] == "admin":
        print(
            "error: 'admin' is not a recognized command; use 'fleetent platform'", file=sys.stderr
        )
        sys.exit(1)

    if argv and argv[0] == "node":
        if argv[1:2] == ["start"]:
            from fleetent.node import app as node_app

            node_app.main()
            return
        if argv[1:2] == ["init-config"]:
            from fleetent.node import init_config as node_init_config

            node_init_config.main(argv[2:])
            return
        print("Usage: fleetent node start | fleetent node init-config", file=sys.stderr)
        sys.exit(1)

    if argv and argv[0] == "chat":
        from fleetent.tui import app as tui_app

        tui_app.main(argv[1:])
        return

    if argv and argv[0] == "kb":
        if argv[1:2] == ["worker"]:
            from fleetent.knowledge_base import worker as kb_worker

            kb_worker.main(argv[2:])
            return
        if argv[1:2] == ["init-config"]:
            from fleetent.knowledge_base import service_init_config

            service_init_config.main(argv[2:])
            return
        if argv[1:2] == ["serve"]:
            from fleetent.knowledge_base import serve as kb_serve

            kb_serve.main(argv[2:])
            return
        if argv[1:2] == ["ingest"]:
            from fleetent.knowledge_base import ingest_cli

            ingest_cli.main(argv[2:])
            return
        if argv[1:2] == ["create"]:
            from fleetent.knowledge_base import create_cli

            create_cli.main(argv[2:])
            return
        if argv[1:2] == ["reindex"]:
            from fleetent.knowledge_base import reindex_cli

            reindex_cli.main(argv[2:])
            return
        if argv[1:2] == ["extract"]:
            from fleetent.knowledge_base import extract_cli

            extract_cli.main(argv[2:])
            return
        print(
            "Usage: fleetent kb serve|worker|ingest|create|reindex|extract|init-config",
            file=sys.stderr,
        )
        sys.exit(1)

    if argv and argv[0] in {
        "kb-worker",
        "kb-service",
        "kb-serve",
        "kb-ingest",
        "kb-create",
        "kb-reindex",
        "kb-extract",
    }:
        print(
            "Usage: fleetent kb serve|worker|ingest|create|reindex|extract|init-config",
            file=sys.stderr,
        )
        sys.exit(1)

    user_input = " ".join(argv) if argv else sys.stdin.read().strip()
    if not user_input:
        print(
            "Usage: fleetent <prompt>  |  fleetent agent run <agent-id> [--port N]",
            file=sys.stderr,
        )
        sys.exit(1)

    # Slash commands go through the shared dispatcher before the loop. CLI one-shot is
    # stateless (session_id=None), so /user works but session commands return a hint.
    from fleetent import agent_config
    from fleetent.runtime.commands import CommandContext, handle_command

    agent_config.scan()
    agent_id = agent_config.current().default_agent()
    ctx = CommandContext(agent_name=agent_id, session_id=None, user_id="default")
    cmd_reply = asyncio.run(handle_command(ctx, user_input))
    if cmd_reply is not None:
        print(cmd_reply)
        return

    print(run(user_input))


if __name__ == "__main__":
    main()
