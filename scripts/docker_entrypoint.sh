#!/usr/bin/env bash
set -euo pipefail

if [ "${FLEETENT_AUTO_UPGRADE:-false}" = "true" ]; then
  uv run fleetent platform upgrade
fi

exec uv run fleetent platform serve --host 0.0.0.0 --port 8765
