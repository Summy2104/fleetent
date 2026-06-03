#!/usr/bin/env bash
set -euo pipefail

if [ "${FLEETENT_AUTO_UPGRADE:-false}" = "true" ]; then
  uv run python scripts/upgrade.py
fi

exec uv run uvicorn fleetent.server:app --host 0.0.0.0 --port 8765
