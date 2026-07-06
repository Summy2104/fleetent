"""CLI for workflows: ``fleetent workflow list`` and ``fleetent workflow run``.

The run path shares the same ``engine.start_run`` entry as the tool path (no second
start code path); it binds the agent-side DB, drives the run to a terminal state,
and prints the per-step result — for dev and the no-platform verification baseline.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

from fleetent import paths, workflow
from fleetent.workflow import store
from fleetent.workflow.engine import WorkflowEngine
from fleetent.workflow.errors import WorkflowError


def main(argv: list[str]) -> None:
    if argv[:1] == ["list"]:
        _cmd_list()
        return
    if argv[:1] == ["run"]:
        _cmd_run(argv[1:])
        return
    print(
        "Usage: fleetent workflow list | fleetent workflow run <name> [--input k=v ...]",
        file=sys.stderr,
    )
    sys.exit(1)


def _cmd_list() -> None:
    entries = workflow.list_definitions()
    if not entries:
        print("(no workflows found)")
        return
    for e in entries:
        status = "ok" if e["valid"] else f"INVALID: {e['error']}"
        print(f"{e['name']}: {status}")


def _cmd_run(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="fleetent workflow run")
    parser.add_argument("name", help="workflow name (file stem in the workflows dir)")
    parser.add_argument(
        "--input", action="append", default=[], metavar="k=v", help="a start input (repeatable)"
    )
    parser.add_argument("--home", default=None, help="override the agent home directory")
    parser.add_argument("--agent", default="default", help="agent id whose state DB to use")
    ns = parser.parse_args(argv)

    inputs = _parse_inputs(ns.input)
    _bind_state_db(agent_id=ns.agent, home=ns.home)
    try:
        wf = workflow.load_definition(ns.name)
    except WorkflowError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    engine = WorkflowEngine(agent_name=ns.agent)
    try:
        run_id = engine.start_run(wf, inputs=inputs, origin={"platform": "cli", "chat_id": ""})
    except WorkflowError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
    asyncio.run(engine.drive_run(run_id))
    _print_result(run_id)


def _parse_inputs(pairs: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for pair in pairs:
        if "=" not in pair:
            print(f"error: --input must be k=v, got {pair!r}", file=sys.stderr)
            sys.exit(1)
        key, value = pair.split("=", 1)
        out[key] = value
    return out


def _bind_state_db(*, agent_id: str, home: str | None) -> None:
    from fleetent.runtime import agent_app

    data_dir = Path(home) / "data" if home is not None else paths.agent_data_dir(agent_id)
    agent_app._init_agent_db_schema(data_dir, agent_name=agent_id)


def _print_result(run_id: str) -> None:
    run = store.get_run(run_id)
    if run is None:
        print(f"run {run_id} vanished", file=sys.stderr)
        return
    print(f"run {run_id} [{run['status']}]")
    for step in store.list_steps(run_id):
        suffix = f" — {step['error']}" if step.get("error") else ""
        out = step.get("output")
        out_txt = f" output={out}" if out is not None else ""
        print(f"  {step['step_id']} [{step['status']}]{suffix}{out_txt}")
