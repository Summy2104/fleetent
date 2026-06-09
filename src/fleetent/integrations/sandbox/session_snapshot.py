"""Sandbox session shell-environment snapshot (sandbox-session-snapshot).

Pure helpers that make ``docker exec`` environment-continuous across calls: capture
the login-shell environment once, then wrap each subsequent command as
``source snapshot -> cd -> eval -> re-dump -> print cwd marker``. The orchestration
that runs these (with fall-back to a login shell on failure) lives in
``SandboxClient.exec``; everything here is pure string building so it is unit-testable
without docker.
"""

from __future__ import annotations

import re
import shlex

_SAFE = re.compile(r"[^a-zA-Z0-9_.-]")
_SNAP_PATH_TPL = "/tmp/snap-{session}.sh"
_CWD_MARKER_TPL = "__FLEETENT_CWD_{session}__"

# Container-side default working directory (the bind-mounted workspace).
DEFAULT_CWD = "/workspace"


def _safe(session_id: str) -> str:
    return _SAFE.sub("-", session_id)[:48]


def snapshot_path(session_id: str) -> str:
    return _SNAP_PATH_TPL.format(session=_safe(session_id))


def cwd_marker(session_id: str) -> str:
    return _CWD_MARKER_TPL.format(session=_safe(session_id))


def build_capture_script(session_id: str) -> str:
    """Login-shell script capturing env/functions/aliases into the snapshot file."""
    snap = snapshot_path(session_id)
    return (
        f"export -p > {snap}; "
        f"declare -f >> {snap} 2>/dev/null || true; "
        f"alias -p >> {snap} 2>/dev/null || true"
    )


def wrap_command(command: str, session_id: str, cwd: str) -> str:
    """Wrap a command to restore snapshot + cwd, run it, re-dump env, print cwd marker.

    The marker-wrapped cwd line is stripped later by ``extract_cwd`` and never reaches
    the caller.
    """
    snap = snapshot_path(session_id)
    marker = cwd_marker(session_id)
    return (
        f"source {snap} 2>/dev/null || true; "
        f"cd {shlex.quote(cwd)} 2>/dev/null || true; "
        f"eval {shlex.quote(command)}; __fe_ec=$?; "
        f"export -p > {snap} 2>/dev/null || true; "
        f"printf '\\n{marker}%s{marker}\\n' \"$(pwd)\"; "
        f"exit $__fe_ec"
    )


def extract_cwd(stdout: str, session_id: str) -> tuple[str | None, str]:
    """Pull the cwd from the LAST marker pair and strip every marker line from output.

    Taking the last pair defends against command output that happens to contain
    marker-like text. Returns ``(cwd_or_None, cleaned_stdout)``.
    """
    marker = cwd_marker(session_id)
    pattern = re.compile(re.escape(marker) + r"(.*?)" + re.escape(marker))
    matches = list(pattern.finditer(stdout))
    if not matches:
        return None, stdout
    cwd = matches[-1].group(1)
    cleaned = pattern.sub("", stdout)
    cleaned = re.sub(r"\n{2,}", "\n", cleaned)
    return cwd, cleaned
