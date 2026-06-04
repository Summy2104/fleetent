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
FLEETENT_HOME_DIR="${FLEETENT_HOME:-$HOME/.fleetent}"
SKIP_DB=false
SKIP_CONFIG=false

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
ensure_uv()              { :; }
check_python()           { :; }
install_tool()           { :; }
setup_home_env()         { :; }
copy_config_templates()  { :; }
init_db()                { :; }
precheck_docker()        { :; }
print_success()          { :; }

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
