#!/bin/bash
# ============================================================================
# fleetent platform control-plane installer
# ============================================================================
# Installs the fleetent binary, initialises the platform database via Alembic,
# and seeds the built-in admin user. Does NOT create any agent home directories.
#
# Usage:
#   scripts/install-platform.sh [--dir PATH] [--skip-db] [--help]
#
# After running, configure the platform:
#   1. Edit $FLEETENT_HOME/.env and $FLEETENT_HOME/platform.yaml
#   2. Start platform: fleetent platform serve --port 8765
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
SKIP_DB=false

usage() {
    cat <<'EOF'
fleetent platform installer — deploy the platform control plane.

Usage:
  scripts/install-platform.sh [options]

Options:
  --dir PATH   Override FLEETENT_HOME (default ~/.fleetent)
  --skip-db    Skip Alembic database initialisation
  --help       Show this help and exit

After installation:
  1. Edit $FLEETENT_HOME/.env  (set FLEETENT_SECRET_KEY etc.)
  2. Edit $FLEETENT_HOME/platform.yaml
  3. Start: fleetent platform serve --port 8765
EOF
}

parse_args() {
    while [ $# -gt 0 ]; do
        case "$1" in
            --help|-h) usage; exit 0 ;;
            --skip-db) SKIP_DB=true; shift ;;
            --dir)
                if [ -z "${2:-}" ]; then
                    log_error "--dir requires a PATH argument"; exit 2
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

install_tool() {
    log_info "Installing fleetent binary (production mode)..."
    uv tool install --force --from "$REPO_ROOT" fleetent
    if ! command -v fleetent >/dev/null 2>&1; then
        log_error "fleetent not found after install."
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

ensure_frontend_toolchain() {
    if command -v node >/dev/null 2>&1 && command -v corepack >/dev/null 2>&1; then
        corepack enable
        return 0
    fi

    if [ "$(uname -s)" != "Linux" ] || ! command -v apt-get >/dev/null 2>&1; then
        log_error "Node.js 22+ with corepack is required to build the admin frontend."
        log_info "Install Node.js 22+ manually, then re-run scripts/install-platform.sh."
        exit 1
    fi

    log_info "Installing Node.js 22 + corepack for admin frontend build..."
    apt-get update
    apt-get install -y curl ca-certificates gnupg
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
    apt-get install -y nodejs
    if ! command -v corepack >/dev/null 2>&1; then
        log_error "corepack was not installed with Node.js. Install Node.js 22+ manually and retry."
        exit 1
    fi
    corepack enable
    log_success "Frontend toolchain ready: $(node --version)"
}

copy_platform_templates() {
    mkdir -p "$FLEETENT_HOME"

    if [ -f "$REPO_ROOT/.env.example" ] && [ ! -f "$FLEETENT_HOME/.env" ]; then
        cp "$REPO_ROOT/.env.example" "$FLEETENT_HOME/.env"
        log_success "Created $FLEETENT_HOME/.env"
    fi

    if [ -f "$REPO_ROOT/platform.yaml.example" ] && [ ! -f "$FLEETENT_HOME/platform.yaml" ]; then
        cp "$REPO_ROOT/platform.yaml.example" "$FLEETENT_HOME/platform.yaml"
        log_success "Created $FLEETENT_HOME/platform.yaml"
    fi

    if [ -f "$FLEETENT_HOME/.env" ] && ! grep -q '^FLEETENT_ADMIN_UI_DIST=' "$FLEETENT_HOME/.env"; then
        printf '\nFLEETENT_ADMIN_UI_DIST=%s/frontend/dist\n' "$REPO_ROOT" >> "$FLEETENT_HOME/.env"
        log_success "Pinned FLEETENT_ADMIN_UI_DIST in $FLEETENT_HOME/.env"
    fi
}

build_admin_frontend() {
    ensure_frontend_toolchain
    log_info "Installing frontend dependencies..."
    make -C "$REPO_ROOT" frontend-install
    log_info "Building admin frontend dist..."
    make -C "$REPO_ROOT" frontend-build
    if [ ! -f "$REPO_ROOT/frontend/dist/index.html" ]; then
        log_error "Admin frontend build finished without frontend/dist/index.html."
        exit 1
    fi
    log_success "Admin frontend dist ready: $REPO_ROOT/frontend/dist"
}

init_platform_db() {
    if [ "$SKIP_DB" = true ]; then
        log_info "Skipping database init (--skip-db)"; return 0
    fi
    mkdir -p "$FLEETENT_HOME"
    log_info "Initialising platform database (alembic upgrade head)..."

    local tmp_ini
    tmp_ini="$(mktemp)"
    sed -e "s|^script_location = .*|script_location = $REPO_ROOT/migrations|" \
        -e "s|^sqlalchemy.url = .*|sqlalchemy.url = sqlite:///$FLEETENT_HOME/management.db|" \
        "$REPO_ROOT/alembic.ini" > "$tmp_ini"

    if uv run --project "$REPO_ROOT" alembic -c "$tmp_ini" upgrade head; then
        log_success "Platform database ready: $FLEETENT_HOME/management.db"
    else
        rm -f "$tmp_ini"
        log_error "Alembic migration failed."; exit 1
    fi
    rm -f "$tmp_ini"
}

seed_admin() {
    log_info "Seeding built-in admin user..."
    if uv run --project "$REPO_ROOT" fleetent platform seed-builtin-admin 2>/dev/null; then
        log_success "Admin seeded (check logs for initial password on first run)"
    else
        log_warn "seed-builtin-admin returned non-zero (may already exist — OK)"
    fi
}

print_success() {
    log_success "Platform installed."
    echo
    echo "Next steps:"
    echo "  1. Edit platform env:  $FLEETENT_HOME/.env"
    echo "  2. Edit platform config: $FLEETENT_HOME/platform.yaml"
    echo "  3. Start platform:     fleetent platform serve --port 8765"
    echo "     /admin/ui will serve the dist pinned by FLEETENT_ADMIN_UI_DIST in .env"
    echo "  4. Add agents:         scripts/install-agent.sh <agent-id>"
}

main() {
    parse_args "$@"
    ensure_uv
    check_python
    install_tool
    setup_home_env
    copy_platform_templates
    build_admin_frontend
    init_platform_db
    seed_admin
    print_success
}

main "$@"
