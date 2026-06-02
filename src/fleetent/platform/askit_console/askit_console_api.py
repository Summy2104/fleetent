"""FastAPI router for /admin/askit — the askit orchestration console.

Exposes askit's commands as a by-series console: list series, trigger a command
(recorded as a task with captured logs + exit code), and review history. The deploy
series is gated on a green check; the migrations series defaults to --dry-run unless
explicitly confirmed; high-risk series require confirmation. askit runs as an external
subprocess via askit_runner (mocked in tests). Never imports the agent loop.

Auth: read-only commands (lint/check/diff/doctor/review) allow viewer+admin; all
other (write) commands require admin.
"""

import asyncio
import json
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from fleetent import auth, user_store
from fleetent.governance import audit_log
from fleetent.platform.agent_management_console import agent_admin_store
from fleetent.platform.askit_console import askit_runner, askit_task_store

router = APIRouter(prefix="/admin/askit")

IDLE_TIMEOUT_SECONDS = 1800
_ADMIN_ROLES = {"admin", "built_in_admin"}

# Commands that mutate state and demand a second confirmation beyond role checks.
_CONFIRM_COMMANDS = {("cron", "install"), ("cron", "remove")}
# High-risk operations that additionally require a current 2FA code when the actor
# has a second factor configured (spec: Deploy / Migrations / promote).
_TWO_FA_COMMANDS = {("override", "promote")}


# --- seam: deploy check gate --------------------------------------------------


def last_check_ok(workspace: str | None) -> bool:
    """Whether the workspace's most recent ``check`` was drift-free. Placeholder = True."""
    return True


# --- auth ---------------------------------------------------------------------


def _current_user(authorization: str | None) -> user_store.User:
    if not authorization or not authorization.startswith("Session "):
        raise HTTPException(status_code=401, detail="not authenticated")
    user_id = auth.validate_session(authorization.split(" ", 1)[1], IDLE_TIMEOUT_SECONDS)
    if user_id is None:
        raise HTTPException(status_code=401, detail="invalid or expired session")
    user = user_store.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid session")
    if not auth.has_role(user, {"viewer", *_ADMIN_ROLES}):
        raise HTTPException(status_code=403, detail="forbidden")
    return user


def _is_admin(user: user_store.User) -> bool:
    return auth.has_role(user, _ADMIN_ROLES)


def _needs_2fa(series: str, command: str) -> bool:
    return askit_runner.is_high_risk(series) or (series, command) in _TWO_FA_COMMANDS


def _enforce_2fa(user: user_store.User, code: str | None) -> None:
    """Require a valid TOTP for high-risk ops when the actor has 2FA configured."""
    if not user.totp_secret:
        return
    if not code or not auth.verify_user_2fa(user.id, code):
        raise HTTPException(status_code=403, detail="2FA verification required")


class RunBody(BaseModel):
    series: str
    command: str
    params: dict[str, Any] | None = None
    workspace: str | None = None
    env: str | None = None


@router.get("/series")
def list_series(authorization: str | None = Header(None)) -> list[dict[str, Any]]:
    _current_user(authorization)
    groups = []
    for series, commands in askit_runner.SERIES.items():
        groups.append(
            {
                "series": series,
                "high_risk": askit_runner.is_high_risk(series),
                "commands": [
                    {"command": c, "readonly": askit_runner.is_readonly(series, c)}
                    for c in commands
                ],
            }
        )
    return groups


@router.post("/run")
async def run_command(
    body: RunBody,
    authorization: str | None = Header(None),
    x_confirm: str | None = Header(None),
    x_2fa_code: str | None = Header(None, alias="X-2FA-Code"),
) -> dict[str, Any]:
    user = _current_user(authorization)
    if not askit_runner.is_known(body.series, body.command):
        raise HTTPException(status_code=422, detail="unknown series/command")

    readonly = askit_runner.is_readonly(body.series, body.command)
    if not readonly and not _is_admin(user):
        raise HTTPException(status_code=403, detail="admin required for write commands")

    params = dict(body.params or {})
    confirmed = x_confirm == "true"

    # high-risk series require explicit confirmation
    if askit_runner.is_high_risk(body.series) and not confirmed:
        # migrations stay safe by defaulting to dry-run rather than hard-blocking
        if body.series == "migrations":
            params["dry-run"] = True
        else:
            raise HTTPException(
                status_code=428, detail="confirmation required for high-risk command"
            )

    # mutating cron commands need a second confirmation before they run
    if (body.series, body.command) in _CONFIRM_COMMANDS and not confirmed:
        raise HTTPException(status_code=428, detail="confirmation required")

    # high-risk operations also require a current 2FA factor when the actor has one
    if _needs_2fa(body.series, body.command):
        _enforce_2fa(user, x_2fa_code)

    # deploy is gated on a green check
    if body.series == "deploy" and body.command == "deploy" and not last_check_ok(body.workspace):
        raise HTTPException(status_code=409, detail="deploy blocked: latest check is not green")

    # Serial (workspace-mutating) commands queue behind the per-workspace lock; read-only
    # and non-mutating commands run without it so they can proceed concurrently.
    if askit_runner.is_serial(body.series, body.command):
        async with askit_task_store.workspace_lock(body.workspace or "_default"):
            return await _execute(body, params, user.id)
    return await _execute(body, params, user.id)


async def _execute(body: RunBody, params: dict[str, Any], user_id: str) -> dict[str, Any]:
    task_id = askit_task_store.create_task(
        body.series,
        body.command,
        params=params,
        workspace=body.workspace,
        env=body.env,
        created_by=user_id,
    )
    # askit is a blocking subprocess; run it off the event loop so concurrent read-only
    # commands are not stalled by a long-running one.
    result = await asyncio.to_thread(askit_runner.run, body.series, body.command, params)
    seq = 0
    for stream in ("stdout", "stderr"):
        for line in (result.get(stream) or "").splitlines():
            askit_task_store.append_log(task_id, seq, stream, line)
            seq += 1
    status = "succeeded" if result["exit_code"] == 0 else "failed"
    askit_task_store.finish_task(task_id, status, result["exit_code"])

    succeeded = result["exit_code"] == 0
    response: dict[str, Any] = {
        "task_id": task_id,
        "status": status,
        "exit_code": result["exit_code"],
        "argv": result["argv"],
        "dry_run": params.get("dry-run", False),
    }
    detail: dict[str, Any] = {
        "exit_code": result["exit_code"],
        "dry_run": params.get("dry-run", False),
        "askit_version": result["askit_version"],
    }

    # Surface structured renderings the UI needs and run provenance/drift side effects.
    # All parsing is over masked stdout, so secrets never reach the response or audit.
    pr_url = _apply_side_effects(body, params, succeeded, result["stdout"], response)
    if pr_url is not None:
        detail["pr_url"] = pr_url

    audit_log.write_audit(
        user_id, f"askit.{body.series}.{body.command}", "askit_task", task_id, detail=detail
    )
    return response


def _apply_side_effects(
    body: RunBody, params: dict[str, Any], succeeded: bool, stdout: str, response: dict[str, Any]
) -> str | None:
    """Enrich the response and run provenance/drift effects; return a PR url if produced."""
    if body.series == "cron" and body.command == "diff":
        response["cron_diff"] = askit_runner.parse_cron_diff(stdout)
    if body.series == "env" and body.command in {"doctor", "env-doctor", "mcp-doctor"}:
        response["diagnostics"] = askit_runner.parse_doctor(stdout)

    agent = params.get("agent")
    if not succeeded or not isinstance(agent, str):
        return None

    if body.series == "override":
        if body.command == "sync":
            agent_admin_store.mark_drift(agent)
        elif body.command == "promote":
            pr_url = askit_runner.extract_pr_url(stdout)
            agent_admin_store.clear_drift(agent)
            response["pr_url"] = pr_url
            return pr_url
        elif body.command == "decompile":
            # ad-hoc -> managed is a flag flip on the same row; agent_id is untouched
            agent_admin_store.set_provenance(agent, "managed")
    elif body.series == "deploy" and body.command == "deploy":
        # spec deploy overwrites any discarded drift and clears the mark
        agent_admin_store.clear_drift(agent)
    return None


@router.get("/tasks/{task_id}")
def task_detail(task_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    _current_user(authorization)
    task = askit_task_store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return {"task": task, "logs": askit_task_store.get_logs(task_id)}


@router.get("/tasks/{task_id}/stream")
def task_log_stream(task_id: str, authorization: str | None = Header(None)) -> StreamingResponse:
    """Replay a task's persisted log lines as SSE, then a final event with the exit code.

    Tasks run to completion synchronously before the run endpoint returns, so this
    streams the stored history (history-replay) rather than tailing a live process.
    """
    _current_user(authorization)
    task = askit_task_store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")

    def _events() -> Iterator[str]:
        for log in askit_task_store.get_logs(task_id):
            yield f"data: {json.dumps(log)}\n\n"
        end = {"event": "end", "status": task["status"], "exit_code": task["exit_code"]}
        yield f"data: {json.dumps(end)}\n\n"

    return StreamingResponse(_events(), media_type="text/event-stream")


@router.get("/tasks")
def recent_tasks(authorization: str | None = Header(None)) -> list[dict[str, Any]]:
    _current_user(authorization)
    return askit_task_store.list_recent()
