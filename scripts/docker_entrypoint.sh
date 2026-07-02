#!/usr/bin/env bash
set -euo pipefail

role="${1:-platform}"
if [ "$#" -gt 0 ]; then
  shift
fi

case "$role" in
  platform)
    if [ "${FLEETENT_AUTO_UPGRADE:-false}" = "true" ]; then
      fleetent platform upgrade
    fi
    if [ "$#" -gt 0 ]; then
      exec fleetent platform "$@"
    fi
    exec fleetent platform serve --host 0.0.0.0 --port 8765
    ;;
  node)
    exec fleetent node start "$@"
    ;;
  kb-worker)
    exec fleetent kb worker "$@"
    ;;
  agent)
    exec fleetent agent run "$@"
    ;;
  fleetent)
    exec fleetent "$@"
    ;;
  *)
    echo "unsupported role: $role (expected: platform, node, kb-worker, agent)" >&2
    exit 64
    ;;
esac
