#!/bin/bash
# ============================================================================
# fleetent agent host installer
# ============================================================================
# Installs the fleetent binary and node supervisor, sets FLEETENT_HOME, then
# prints a tutorial guiding you to configure the node against a platform. It
# does NOT create an agent home and does NOT require alembic.
#
# Usage:
#   scripts/install-agent.sh [--dir PATH] [--help]
#
# After running, configure and start the node:
#   mkdir -p "$FLEETENT_HOME/node"
#   $EDITOR "$FLEETENT_HOME/node/.env"
#   fleetent node start
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

usage() {
    cat <<'EOF'
fleetent agent host installer — install the runtime + node supervisor, then set
FLEETENT_HOME for a managed agent host.

Usage:
  scripts/install-agent.sh [options]

Options:
  --dir PATH  Override FLEETENT_HOME (default ~/.fleetent)
  --help      Show this help and exit

After installation, connect this host to platform:
  1. mkdir -p "$FLEETENT_HOME/node"
  2. Create $FLEETENT_HOME/node/.env with:
       FLEETENT_NODE_PLATFORM_URL=https://platform.example.com
       FLEETENT_NODE_ID=<node-id>
       FLEETENT_NODE_SERVICE_KEY=ma-<service-key>
  3. fleetent node start

For local dev/test only:
  - fleetent agent init <agent-id>
  - fleetent agent run <agent-id> [--port N]

Note: the old <agent-id> positional argument was removed. Production deployment
goes through node; agent init/run remain available for dev/test.
EOF
}

parse_args() {
    while [ $# -gt 0 ]; do
        case "$1" in
            --help|-h) usage; exit 0 ;;
            --dir)
                if [ -z "${2:-}" ]; then
                    log_error "--dir requires a PATH argument"; exit 2
                fi
                FLEETENT_HOME_DIR="$2"; shift 2 ;;
            -*)
                log_error "Unknown option: $1"; usage >&2; exit 2 ;;
            *)
                log_error "The agent-id argument was removed. Configure node via $FLEETENT_HOME/node/.env and start with fleetent node start."
                usage >&2; exit 2 ;;
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
        log_error "Python >=3.12 is required and uv could not provide it."
        exit 1
    fi
}

install_tool() {
    log_info "Installing fleetent binary (production mode)..."
    # --from . for production: binary is self-contained, no source dir needed at runtime.
    uv tool install --force --from "$REPO_ROOT" fleetent
    if ! command -v fleetent >/dev/null 2>&1; then
        log_error "fleetent not found after install. Ensure ~/.local/bin is on PATH."
        log_info "Run: uv tool update-shell"
        exit 1
    fi
    log_success "Installed: fleetent"
}

setup_home_env() {
    export FLEETENT_HOME="$FLEETENT_HOME_DIR"
    mkdir -p "$FLEETENT_HOME"
    log_info "FLEETENT_HOME = $FLEETENT_HOME"

    local rc
    case "$(basename "${SHELL:-/bin/bash}")" in
        zsh)  rc="$HOME/.zshrc" ;;
        bash) rc="$HOME/.bashrc" ;;
        *)    rc="$HOME/.profile" ;;
    esac
    if [ ! -f "$rc" ] || ! grep -qF "export FLEETENT_HOME=" "$rc"; then
        echo "export FLEETENT_HOME=\"$FLEETENT_HOME\"" >> "$rc"
        log_success "Persisted FLEETENT_HOME to $rc"
    fi
}

precheck_docker() {
    if command -v docker >/dev/null 2>&1; then return 0; fi
    log_warn "Docker not found — the sandbox (run_code) tool will be unavailable."
}

print_tutorial() {
    log_success "fleetent runtime + node supervisor installed.  FLEETENT_HOME = $FLEETENT_HOME"
    echo
    echo "Next — configure this agent host's node supervisor and connect it to platform:"
    echo "  1. mkdir -p \"$FLEETENT_HOME/node\""
    echo "  2. Create \$FLEETENT_HOME/node/.env with:"
    echo "       FLEETENT_NODE_PLATFORM_URL=https://platform.example.com"
    echo "       FLEETENT_NODE_ID=<node-id>"
    echo "       FLEETENT_NODE_SERVICE_KEY=ma-<service-key>"
    echo "  3. fleetent node start"
    echo
    echo "Local dev/test only:"
    echo "  - fleetent agent init <agent-id>"
    echo "  - fleetent agent run <agent-id> [--port 8766]"
}

main() {
    parse_args "$@"
    ensure_uv
    check_python
    install_tool
    setup_home_env
    precheck_docker
    print_tutorial
}

main "$@"
