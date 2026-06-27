"""Provision a local dev node: register it, then write ``$FLEETENT_HOME/node/.env``.

Node registration is a direct admin-CLI write to the management DB (per the CLI /
platform boundary: node supply is an allowed CLI direct-write), so it needs neither
a running platform nor an admin login — only ``FLEETENT_HOME`` / ``DATABASE_URL`` in
the environment (the Makefile dev-stack targets export both).

Idempotent: if ``node/.env`` already carries a service key it is left untouched (the
key is shown only once at registration). ``--force`` deregisters and re-registers,
minting a fresh key.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

_KEY_RE = re.compile(r"service_key:\s*(ma-[0-9a-f]+)")


def _home_dir() -> Path:
    return Path(os.environ.get("FLEETENT_HOME") or Path.home() / ".fleetent").expanduser()


def _run_admin(*args: str) -> subprocess.CompletedProcess[str]:
    # python -m fleetent re-dispatches to the platform CLI under the active interpreter.
    return subprocess.run(
        [sys.executable, "-m", "fleetent", "platform", "node", *args],
        capture_output=True,
        text=True,
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="dev_node_provision")
    parser.add_argument("--node-id", default=os.environ.get("NODE_ID", "local-node"))
    parser.add_argument(
        "--platform-url",
        default=os.environ.get("NODE_PLATFORM_URL", "http://127.0.0.1:8765"),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="deregister + re-register even if node/.env already exists",
    )
    ns = parser.parse_args(argv)

    env_path = _home_dir() / "node" / ".env"
    if (
        env_path.exists()
        and "FLEETENT_NODE_SERVICE_KEY=ma-" in env_path.read_text(encoding="utf-8")
        and not ns.force
    ):
        print(f"node already provisioned: {env_path} (use --force to re-register)")
        return

    if ns.force:
        _run_admin("deregister", ns.node_id)  # best-effort; ignore "not found"

    result = _run_admin("register", ns.node_id, "--name", "Local Dev Node")
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    if result.returncode != 0:
        sys.exit(
            f"node register failed (rc={result.returncode}); "
            "if it is already registered, re-run with --force"
        )
    match = _KEY_RE.search(result.stdout)
    if match is None:
        sys.exit("could not parse service_key from register output")
    service_key = match.group(1)

    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text(
        f"FLEETENT_NODE_PLATFORM_URL={ns.platform_url}\n"
        f"FLEETENT_NODE_ID={ns.node_id}\n"
        f"FLEETENT_NODE_SERVICE_KEY={service_key}\n"
        "FLEETENT_NODE_INTERVAL_SECONDS=10\n",
        encoding="utf-8",
    )
    print(f"✓ wrote {env_path} (node {ns.node_id} → {ns.platform_url})")


if __name__ == "__main__":
    main()
