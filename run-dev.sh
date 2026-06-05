#!/usr/bin/env bash
# run-dev.sh — load .env, ensure the DB schema, start the fleetent dev server.
#
# Why this exists: model_router reads provider keys from os.environ (NOT from
# .env directly), so .env must be exported into the environment before launch.
# This script does that, applies any pending migrations, then runs the server.
#
# Usage:
#   ./run-dev.sh                 # start on port 8765
#   PORT=9000 ./run-dev.sh       # custom port
#   ./run-dev.sh --reload        # extra args are passed through to uvicorn
#
# Then, in another terminal, connect the TUI:
#   uv run fleetent-tui --token ma-<your-key>
set -euo pipefail

# Always operate from the project root (this script's directory).
cd "$(dirname "$0")"

PORT="${PORT:-8765}"

# 1) Load .env into the environment (export every var so the model router sees keys).
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
  echo "✓ loaded .env"
else
  echo "⚠ no .env found — copy .env.example to .env and set your keys" >&2
fi

# 2) Ensure the DB schema is current (idempotent; a no-op when already at head).
echo "→ alembic upgrade head"
uv run alembic upgrade head

# 3) Start the server in the foreground (Ctrl-C stops it).
echo
echo "Server → http://127.0.0.1:${PORT}   (Ctrl-C to stop)"
echo "TUI (another terminal): uv run fleetent-tui --token ma-..."
echo
exec uv run uvicorn fleetent.server:app --port "${PORT}" "$@"
