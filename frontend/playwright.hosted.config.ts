import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { defineConfig } from '@playwright/test';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, '..');
const smokePort = 8876;
const smokeDir = path.join(repoRoot, '.playwright-admin');

const webServerCommand = `bash -lc '
set -euo pipefail
rm -rf "${smokeDir}"
mkdir -p "${smokeDir}"
export FLEETENT_HOME="${smokeDir}/home"
export DATABASE_URL="sqlite:///${smokeDir}/management.db"
export ANTHROPIC_API_KEY="test-key"
yarn --cwd frontend build >/dev/null
uv run alembic upgrade head >/dev/null
uv run python - <<'"'"'PY'"'"'
import fleetent.agent_store as agent_store
import fleetent.auth as auth
import fleetent.platform.agent_management_console.agent_admin_store as agent_admin_store
import fleetent.user_store as user_store

user = user_store.get_by_email("admin@example.com")
user = user or user_store.create_web_user(
    "admin@example.com",
    "Admin",
    password_hash=auth.hash_password("adminpw"),
    role="admin",
)
user_store.set_password(user.id, auth.hash_password("adminpw"), must_reset=False)
user_store.set_role(user.id, "admin")
agent = agent_store.get_by_name("alpha") or agent_store.create_agent("alpha", "Alpha prompt", ["read_file"])
agent_admin_store.set_provenance(agent.id, "adhoc")
agent_admin_store.enable(agent.id)
PY
uv run python -m uvicorn fleetent.server:app --host 127.0.0.1 --port ${smokePort}
'`;

export default defineConfig({
  testDir: './e2e',
  testMatch: /agents-hosted\.spec\.ts/,
  use: {
    baseURL: `http://127.0.0.1:${smokePort}`,
    trace: 'retain-on-failure',
  },
  webServer: {
    command: webServerCommand,
    cwd: repoRoot,
    reuseExistingServer: false,
    url: `http://127.0.0.1:${smokePort}/health`,
  },
});
