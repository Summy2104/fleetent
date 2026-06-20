#!/bin/bash
# ============================================================================
# fleetent one-click installer (developers / single machine)
# ============================================================================
# Installs BOTH the platform control plane and a default standalone agent in
# editable mode — suitable for local development where the source tree must
# stay as the live import path.
#
# For production deployment use the role-specific scripts instead:
#   scripts/install-agent.sh <agent-id>   — standalone agent only
#   scripts/install-platform.sh           — platform control plane only
#
# Usage:
#   scripts/install.sh [--agent-only] [--platform-only]
#                      [--agent-id ID] [--dir PATH] [--help]
# ============================================================================

set -e

if [ -n "${PYTHONPATH:-}" ]; then unset PYTHONPATH; fi
if [ -n "${PYTHONHOME:-}" ]; then unset PYTHONHOME; fi

# ── Colors / logging ────────────────────────────────────────────────────────
if [ -t 1 ]; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; BLUE='\033[0;34m'; NC='\033[0m'
else
    RED=''; GREEN=''; YELLOW=''; BLUE=''; NC=''
fi
log_info()    { printf "${BLUE}==>${NC} %s\n" "$1"; }
log_success() { printf "${GREEN}✓${NC} %s\n" "$1"; }
log_warn()    { printf "${YELLOW}⚠${NC} %s\n" "$1" >&2; }
log_error()   { printf "${RED}✗${NC} %s\n" "$1" >&2; }

# ── Configuration ────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
FLEETENT_HOME_DIR="${FLEETENT_HOME:-$HOME/.fleetent}"
INSTALL_AGENT=true
INSTALL_PLATFORM=true

usage() {
    cat <<'EOF'
fleetent developer installer — install both agent runtime and platform in editable mode.

Usage:
  scripts/install.sh [options]

Options:
  --agent-only        Install only the standalone agent runtime
  --platform-only     Install only the platform control plane
  --dir PATH          Override FLEETENT_HOME (default ~/.fleetent)
  --help              Show this help and exit

Agent creation is a separate step (no default agent is seeded):
  fleetent agent init <agent-id>

For production deployment use role-specific scripts:
  scripts/install-agent.sh
  scripts/install-platform.sh
EOF
}

parse_args() {
    while [ $# -gt 0 ]; do
        case "$1" in
            --help|-h) usage; exit 0 ;;
            --agent-only)   INSTALL_PLATFORM=false; shift ;;
            --platform-only) INSTALL_AGENT=false; shift ;;
            --dir)
                if [ -z "${2:-}" ]; then
                    log_error "--dir requires a PATH"; exit 2
                fi
                FLEETENT_HOME_DIR="$2"; shift 2 ;;
            *)
                log_error "Unknown option: $1"; usage >&2; exit 2 ;;
        esac
    done
}

ensure_uv() {
    if command -v uv >/dev/null 2>&1; then return 0; fi
    if [ -x "$HOME/.local/bin/uv" ]; then export PATH="$HOME/.local/bin:$PATH"; return 0; fi
    if [ -x "$HOME/.cargo/bin/uv" ]; then export PATH="$HOME/.cargo/bin:$PATH"; return 0; fi
    log_info "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
}

check_python() {
    if ! uv python find ">=3.12" >/dev/null 2>&1; then
        log_error "Python >=3.12 is required."; exit 1
    fi
}

install_editable() {
    log_info "Installing fleetent in editable mode (developer)..."
    # --editable: source tree stays the live import path.
    uv tool install --force --editable "$REPO_ROOT"
    log_success "Installed (editable): fleetent"
}

main() {
    parse_args "$@"
    ensure_uv
    check_python
    install_editable

    export FLEETENT_HOME="$FLEETENT_HOME_DIR"

    if [ "$INSTALL_PLATFORM" = true ]; then
        log_info "Setting up platform..."
        bash "$SCRIPT_DIR/install-platform.sh" \
            --dir "$FLEETENT_HOME_DIR" --skip-db 2>/dev/null || true
        # Run db init ourselves since binary is already installed.
        mkdir -p "$FLEETENT_HOME/data"
        local tmp_ini
        tmp_ini="$(mktemp)"
        sed -e "s|^script_location = .*|script_location = $REPO_ROOT/migrations|" \
            -e "s|^sqlalchemy.url = .*|sqlalchemy.url = sqlite:///$FLEETENT_HOME/data/management.db|" \
            "$REPO_ROOT/alembic.ini" > "$tmp_ini"
        uv run --project "$REPO_ROOT" alembic -c "$tmp_ini" upgrade head \
            && log_success "Platform database ready"
        rm -f "$tmp_ini"
    fi

    if [ "$INSTALL_AGENT" = true ]; then
        # install-defer-agent-init: the runtime is already installed (editable, above);
        # no default agent is seeded — print the create-agent tutorial instead.
        log_info "Agent runtime ready (no default agent seeded)."
        echo
        echo "Create and run an agent:"
        echo "  1. fleetent agent init <agent-id>"
        echo "  2. Edit $FLEETENT_HOME/agents/<agent-id>/agent.yaml + .env   (chmod 600 .env)"
        echo "  3. fleetent agent run <agent-id> [--port 8766]"
        echo "  4. fleetent chat --url ws://localhost:<port>/ws --token <FLEETENT_TUI_TOKEN>"
        echo
    fi

    log_success "Developer install complete."
    echo
    echo "Editable install: changes in $REPO_ROOT/src take effect immediately."
    echo "State / config:   $FLEETENT_HOME"
}

main "$@"
