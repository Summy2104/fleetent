"""askit CLI subprocess wrapper — command mapping, arg whitelist, output masking.

askit (ai-skills-toolkit) is an external tool. This module maps the console's
series/command to a fixed allowlisted argv (no arbitrary injection), runs it through
an injectable subprocess seam (mockable in tests), and masks sensitive values from
captured output. The askit version is pinned in the image and reported for audit.
"""

import re
from typing import Any

ASKIT_VERSION = "pinned-in-image"  # read out for audit; set at image build

# series -> {command: allowed argv tail}. Commands not in this map are rejected.
SERIES: dict[str, dict[str, list[str]]] = {
    "authoring": {
        "init-repo": ["init-repo"],
        "new-agent": ["new-agent"],
        "new-skill": ["new-skill"],
        "init-from-excel": ["init-from-excel"],
    },
    "build": {
        "build": ["build"],
        "lint": ["lint"],
        "check": ["check"],
        "audit": ["audit"],
        "catalog-export": ["catalog", "export"],
    },
    "deploy": {"deploy": ["deploy"], "provision": ["provision"]},
    "deps": {"install": ["install"]},
    "override": {
        "sync": ["override", "sync"],
        "review": ["override", "review"],
        "promote": ["override", "promote"],
        "discard": ["override", "discard"],
        "cleanup": ["override", "cleanup"],
        "decompile": ["decompile"],
    },
    "cron": {
        "list": ["cron", "list"],
        "diff": ["cron", "diff"],
        "install": ["cron", "install"],
        "remove": ["cron", "remove"],
    },
    "env": {
        "doctor": ["doctor"],
        "env-doctor": ["env", "doctor"],
        "env-sync": ["env-sync"],
        "mcp-doctor": ["mcp", "doctor"],
        "sync-allowlist": ["sync", "allowlist"],
    },
    "migrations": {
        "migrate-openclaw-overrides": ["migrate-openclaw-overrides"],
        "migrate-shared-identity": ["migrate-shared-identity"],
        "migrate-env": ["migrate-env"],
    },
}

# series that mutate the workspace/targets (serialized + high-risk where noted)
WRITE_SERIES = {"authoring", "build", "deploy", "deps", "override", "cron", "env", "migrations"}
READONLY_COMMANDS = {
    ("build", "lint"),
    ("build", "check"),
    ("build", "audit"),
    ("build", "catalog-export"),
    ("override", "review"),
    ("cron", "list"),
    ("cron", "diff"),
    ("env", "doctor"),
    ("env", "env-doctor"),
    ("env", "mcp-doctor"),
}
HIGH_RISK_SERIES = {"deploy", "migrations"}
SERIAL_COMMANDS = {("build", "build"), ("deploy", "deploy"), ("override", "promote")}

_SENSITIVE_RE = re.compile(r"(?i)\b(\w*(?:token|secret|password|api[_-]?key)\w*)\b\s*[:=]\s*\S+")


def is_known(series: str, command: str) -> bool:
    return command in SERIES.get(series, {})


def is_readonly(series: str, command: str) -> bool:
    return (series, command) in READONLY_COMMANDS


def is_high_risk(series: str) -> bool:
    return series in HIGH_RISK_SERIES


def build_command(series: str, command: str, params: dict[str, Any] | None = None) -> list[str]:
    """Build an allowlisted argv. Rejects unknown series/command and odd param values."""
    if not is_known(series, command):
        raise ValueError(f"unknown askit command: {series}/{command}")
    argv = ["askit", *SERIES[series][command]]
    for key, value in (params or {}).items():
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", str(key)):
            raise ValueError(f"illegal param name: {key}")
        flag = f"--{key}"
        if value is True:
            argv.append(flag)
        elif value is False or value is None:
            continue
        else:
            if not re.fullmatch(r"[a-zA-Z0-9_./:@=-]+", str(value)):
                raise ValueError(f"illegal param value for {key}")
            argv.extend([flag, str(value)])
    return argv


def mask_output(text: str) -> str:
    """Redact key=value / key: value pairs whose key looks sensitive."""
    return _SENSITIVE_RE.sub(lambda m: f"{m.group(1)}=****", text)


def run_subprocess(argv: list[str]) -> tuple[str, str, int]:
    """Execute askit. Placeholder seam — monkeypatched in tests; wired on host."""
    raise RuntimeError("askit subprocess not wired in this environment")


def run(series: str, command: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build + run a command, returning masked stdout/stderr and exit code."""
    argv = build_command(series, command, params)
    stdout, stderr, code = run_subprocess(argv)
    return {
        "argv": argv,
        "stdout": mask_output(stdout),
        "stderr": mask_output(stderr),
        "exit_code": code,
        "askit_version": ASKIT_VERSION,
    }
