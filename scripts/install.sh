#!/bin/bash
# ============================================================================
# fleetent one-click installer (developers / single machine)
# ============================================================================
# Bootstraps a globally-usable, working-directory-decoupled fleetent install on
# Linux / macOS / WSL2:
#   - provisions uv + a Python 3.12 runtime
#   - installs the fleetent / fleetent-admin / fleetent-tui commands globally
#     via `uv tool install`
#   - fixes state under FLEETENT_HOME (default ~/.fleetent): config templates +
#     Alembic-initialised database
#
# NOTE: This is for developer / single-machine use. For on-prem PRODUCTION
# deployment use the Docker path (Dockerfile + docker-compose.yml), which keeps
# the environment reproducible and data inside the customer network.
#
# Usage:
#   scripts/install.sh [--skip-db] [--skip-config] [--dir PATH] [--help]
# ============================================================================

set -e

# Drop inherited Python env that could shadow the modules we install (a pre-set
# PYTHONPATH from the launching tool makes entrypoints import a different
# checkout). POSIX-only concern; harmless to always clear.
if [ -n "${PYTHONPATH:-}" ]; then
    unset PYTHONPATH
fi
if [ -n "${PYTHONHOME:-}" ]; then
    unset PYTHONHOME
fi

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

# ── Configuration / flags ───────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
FLEETENT_HOME_DIR="${FLEETENT_HOME:-$HOME/.fleetent}"
SKIP_DB=false
SKIP_CONFIG=false
ENTRYPOINTS="fleetent fleetent-admin fleetent-tui"

usage() {
    cat <<'EOF'
fleetent installer — bootstrap a global, working-directory-decoupled install.

Usage:
  scripts/install.sh [options]

Options:
  --dir PATH      Override FLEETENT_HOME (state directory; default ~/.fleetent)
  --skip-db       Skip Alembic database initialization
  --skip-config   Skip copying config templates
  --help          Show this help and exit

For on-prem production deployment use the Docker path instead
(Dockerfile + docker-compose.yml).
EOF
}

parse_args() {
    while [ $# -gt 0 ]; do
        case "$1" in
            --help|-h)
                usage
                exit 0
                ;;
            --skip-db)
                SKIP_DB=true
                shift
                ;;
            --skip-config)
                SKIP_CONFIG=true
                shift
                ;;
            --dir)
                if [ -z "${2:-}" ]; then
                    log_error "--dir requires a PATH argument"
                    usage >&2
                    exit 2
                fi
                FLEETENT_HOME_DIR="$2"
                shift 2
                ;;
            *)
                log_error "Unknown option: $1"
                usage >&2
                exit 2
                ;;
        esac
    done
}

# ── Steps (filled in by later tasks) ────────────────────────────────────────
detect_os()              { :; }

# Reuse uv from PATH or its standard install locations; only fetch if absent.
ensure_uv() {
    if command -v uv >/dev/null 2>&1; then
        return 0
    fi
    if [ -x "$HOME/.local/bin/uv" ]; then
        export PATH="$HOME/.local/bin:$PATH"
        return 0
    fi
    if [ -x "$HOME/.cargo/bin/uv" ]; then
        export PATH="$HOME/.cargo/bin:$PATH"
        return 0
    fi
    log_info "Installing uv (fast Python package manager)..."
    if ! curl -LsSf https://astral.sh/uv/install.sh | sh; then
        log_error "uv install failed. Install it manually: https://docs.astral.sh/uv/"
        exit 1
    fi
    export PATH="$HOME/.local/bin:$PATH"
}

# uv provisions the interpreter; fail fast if a >=3.12 runtime can't be found.
check_python() {
    if ! uv python find ">=3.12" >/dev/null 2>&1; then
        log_error "Python >=3.12 is required and uv could not provide it."
        exit 1
    fi
}

# Install the three console-script entrypoints globally (into ~/.local/bin),
# editable so the dev checkout stays the source of truth.
install_tool() {
    log_info "Installing fleetent commands via uv tool..."
    uv tool install --force --editable "$REPO_ROOT"
    for cmd in $ENTRYPOINTS; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            log_error "Expected command '$cmd' not found after install."
            log_info "Try manually: uv tool install --editable \"$REPO_ROOT\""
            log_info "Ensure ~/.local/bin is on your PATH (uv tool update-shell)."
            exit 1
        fi
    done
    log_success "Installed: $ENTRYPOINTS"
}

# Fix the state directory (FLEETENT_HOME) and persist it to the user's shell rc
# so the global command resolves config/data there regardless of CWD.
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
    # Idempotent: only append if no FLEETENT_HOME export is already present.
    if [ ! -f "$rc" ] || ! grep -qF "export FLEETENT_HOME=" "$rc"; then
        echo "export FLEETENT_HOME=\"$FLEETENT_HOME\"" >> "$rc"
        log_success "Persisted FLEETENT_HOME to $rc"
    fi

    case ":$PATH:" in
        *":$HOME/.local/bin:"*) : ;;
        *) log_warn "~/.local/bin is not on your PATH — add it (e.g. 'uv tool update-shell') to run the fleetent command." ;;
    esac
}
# Seed the deployed agent config and env. The agent runtime reads config/agent.yaml,
# .env, and local data/. Global settings/mcp files are not seeded — their loaders
# fall back to defaults when absent.
# Never clobber existing files.
copy_config_templates() {
    if [ "$SKIP_CONFIG" = true ]; then
        log_info "Skipping config templates (--skip-config)"
        return 0
    fi
    mkdir -p "$FLEETENT_HOME"

    if [ -f "$REPO_ROOT/config/agent/.env.example" ] && [ ! -f "$FLEETENT_HOME/.env" ]; then
        cp "$REPO_ROOT/config/agent/.env.example" "$FLEETENT_HOME/.env"
        log_success "Created $FLEETENT_HOME/.env"
    fi

    if [ -f "$REPO_ROOT/config/agent/agent.yaml.example" ] && [ ! -f "$FLEETENT_HOME/agent.yaml" ]; then
        cp "$REPO_ROOT/config/agent/agent.yaml.example" "$FLEETENT_HOME/agent.yaml"
        log_success "Created $FLEETENT_HOME/agent.yaml"
    fi
}
# Initialize the SQLite DB under FLEETENT_HOME via Alembic (idempotent). Schema
# lifecycle stays with Alembic — we only point it at the resolved DB path by
# rewriting a transient copy of the repo's alembic.ini (no env.py changes).
init_db() {
    if [ "$SKIP_DB" = true ]; then
        log_info "Skipping database init (--skip-db)"
        return 0
    fi
    mkdir -p "$FLEETENT_HOME/data"
    log_info "Initializing database (alembic upgrade head)..."

    local tmp_ini
    tmp_ini="$(mktemp)"
    sed -e "s|^script_location = .*|script_location = $REPO_ROOT/migrations|" \
        -e "s|^sqlalchemy.url = .*|sqlalchemy.url = sqlite:///$FLEETENT_HOME/data/fleetent.db|" \
        "$REPO_ROOT/alembic.ini" > "$tmp_ini"

    if uv run --project "$REPO_ROOT" alembic -c "$tmp_ini" upgrade head; then
        log_success "Database ready at $FLEETENT_HOME/data/fleetent.db"
    else
        rm -f "$tmp_ini"
        log_error "Alembic migration failed."
        exit 1
    fi
    rm -f "$tmp_ini"
}
# Sandbox (run_code) needs a host Docker. Absence is a warning, never fatal —
# many dev setups don't use the sandbox.
precheck_docker() {
    if command -v docker >/dev/null 2>&1; then
        return 0
    fi
    log_warn "Docker not found — the sandbox (run_code) tool will be unavailable. Install Docker to enable it."
}
print_success() {
    log_success "fleetent installed."
    echo
    echo "Next steps:"
    echo "  - Ensure ~/.local/bin is on your PATH (e.g. 'uv tool update-shell'),"
    echo "    then open a new shell and run:  fleetent \"hello\""
    echo "  - State / config live in:  $FLEETENT_HOME"
    echo "  - Edit secrets in:  $FLEETENT_HOME/.env"
    echo "  - For on-prem PRODUCTION deployment, use the Docker path (docker-compose.yml)."
}

main() {
    detect_os
    ensure_uv
    check_python
    install_tool
    setup_home_env
    copy_config_templates
    init_db
    precheck_docker
    print_success
}

parse_args "$@"
main
