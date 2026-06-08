#!/bin/bash
# ============================================================================
# fleetent standalone agent installer
# ============================================================================
# Installs the fleetent binary and scaffolds a runnable agent home.
# Does NOT require alembic, fleetent-admin, or a running platform.
#
# Usage:
#   scripts/install-agent.sh <agent-id> [--dir PATH] [--help]
#
# The agent home is created at $FLEETENT_HOME/agents/<agent-id>/.
# After running, edit agent.yaml and .env, then:
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
AGENT_ID=""

usage() {
    cat <<'EOF'
fleetent agent installer — deploy a standalone agent (no platform required).

Usage:
  scripts/install-agent.sh <agent-id> [options]

Arguments:
  agent-id    Required. The agent identifier (e.g. my-bot, support-bot).
              Creates $FLEETENT_HOME/agents/<agent-id>/ with agent.yaml + .env.

Options:
  --dir PATH  Override FLEETENT_HOME (default ~/.fleetent)
  --help      Show this help and exit

After installation:
  1. Edit $FLEETENT_HOME/agents/<agent-id>/agent.yaml (model, system_prompt, connectors)
  2. Fill secrets in $FLEETENT_HOME/agents/<agent-id>/.env
  3. Run: fleetent agent run <agent-id> [--port N]
  4. Connect TUI: fleetent-tui --url ws://localhost:<N>/ws --token <FLEETENT_TUI_TOKEN>
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
                if [ -z "$AGENT_ID" ]; then
                    AGENT_ID="$1"; shift
                else
                    log_error "Unexpected argument: $1"; usage >&2; exit 2
                fi ;;
        esac
    done

    if [ -z "$AGENT_ID" ]; then
        log_error "agent-id is required."
        usage >&2
        exit 2
    fi
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

init_agent() {
    log_info "Initialising agent home for '$AGENT_ID'..."
    if fleetent agent init "$AGENT_ID"; then
        log_success "Agent home created: $FLEETENT_HOME/agents/$AGENT_ID/"
    else
        log_error "fleetent agent init failed."
        exit 1
    fi
}

precheck_docker() {
    if command -v docker >/dev/null 2>&1; then return 0; fi
    log_warn "Docker not found — the sandbox (run_code) tool will be unavailable."
}

print_success() {
    log_success "Agent '$AGENT_ID' installed."
    echo
    echo "Next steps:"
    echo "  1. Edit agent config:  $FLEETENT_HOME/agents/$AGENT_ID/agent.yaml"
    echo "  2. Fill secrets:       $FLEETENT_HOME/agents/$AGENT_ID/.env"
    echo "     (chmod 600 $FLEETENT_HOME/agents/$AGENT_ID/.env)"
    echo "  3. Start agent:        fleetent agent run $AGENT_ID [--port 8766]"
    echo "  4. TUI token in:       $FLEETENT_HOME/agents/$AGENT_ID/.env  (FLEETENT_TUI_TOKEN)"
}

main() {
    parse_args "$@"
    ensure_uv
    check_python
    install_tool
    setup_home_env
    init_agent
    precheck_docker
    print_success
}

main "$@"
