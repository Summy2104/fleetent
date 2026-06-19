#!/bin/bash
# ============================================================================
# fleetent standalone agent runtime installer
# ============================================================================
# Installs the fleetent binary and sets FLEETENT_HOME, then prints a tutorial
# guiding you to create an agent yourself. It does NOT create an agent home and
# does NOT require alembic, fleetent admin, or a running platform.
#
# Usage:
#   scripts/install-agent.sh [--dir PATH] [--help]
#
# After running, create and run an agent:
#   fleetent agent init <agent-id>
#   # edit $FLEETENT_HOME/agents/<agent-id>/agent.yaml + .env
#   fleetent agent run <agent-id> [--port N]
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
fleetent agent runtime installer — install the runtime + set FLEETENT_HOME
(no platform required). Create agents yourself afterwards with `fleetent agent init`.

Usage:
  scripts/install-agent.sh [options]

Options:
  --dir PATH  Override FLEETENT_HOME (default ~/.fleetent)
  --help      Show this help and exit

After installation, create and run an agent:
  1. fleetent agent init <agent-id>
  2. Edit $FLEETENT_HOME/agents/<agent-id>/agent.yaml + .env  (chmod 600 .env)
  3. fleetent agent run <agent-id> [--port N]
  4. fleetent-tui --url ws://localhost:<N>/ws --token <FLEETENT_TUI_TOKEN>

Note: the <agent-id> positional argument was removed — agent creation is now a
separate step (`fleetent agent init`), decoupled from runtime installation.
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
                log_error "The agent-id argument was removed. Create the agent with: fleetent agent init $1"
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
    log_success "Installed: fleetent fleetent-tui"
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
    log_success "fleetent runtime installed.  FLEETENT_HOME = $FLEETENT_HOME"
    echo
    echo "Next — create and run an agent:"
    echo "  1. fleetent agent init <agent-id>"
    echo "  2. Edit $FLEETENT_HOME/agents/<agent-id>/agent.yaml + .env   (chmod 600 .env)"
    echo "  3. fleetent agent run <agent-id> [--port 8766]"
    echo "  4. fleetent-tui --url ws://localhost:<port>/ws --token <FLEETENT_TUI_TOKEN>"
    echo
    echo "(FLEETENT_TUI_TOKEN is generated into the agent's .env by 'fleetent agent init'.)"
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
