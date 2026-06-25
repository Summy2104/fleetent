import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig } from '@playwright/test';
var __dirname = path.dirname(fileURLToPath(import.meta.url));
var repoRoot = path.resolve(__dirname, '..');
var smokePort = 8876;
var smokeDir = path.join(repoRoot, '.playwright-admin');
var webServerCommand = "bash -lc '\nset -euo pipefail\nrm -rf \"".concat(smokeDir, "\"\nmkdir -p \"").concat(smokeDir, "\"\nexport FLEETENT_HOME=\"").concat(smokeDir, "/home\"\nexport DATABASE_URL=\"sqlite:///").concat(smokeDir, "/management.db\"\nexport ANTHROPIC_API_KEY=\"test-key\"\nyarn --cwd frontend build >/dev/null\nuv run alembic upgrade head >/dev/null\nuv run python - <<'\"'\"'PY'\"'\"'\nimport fleetent.agent_store as agent_store\nimport fleetent.auth as auth\nimport fleetent.platform.agent_management_console.agent_admin_store as agent_admin_store\nimport fleetent.user_store as user_store\n\nuser = user_store.get_by_email(\"admin@example.com\")\nuser = user or user_store.create_web_user(\n    \"admin@example.com\",\n    \"Admin\",\n    password_hash=auth.hash_password(\"adminpw\"),\n    role=\"admin\",\n)\nuser_store.set_password(user.id, auth.hash_password(\"adminpw\"), must_reset=False)\nuser_store.set_role(user.id, \"admin\")\nagent = agent_store.get_by_name(\"alpha\") or agent_store.create_agent(\"alpha\", \"Alpha prompt\", [\"read_file\"])\nagent_admin_store.set_provenance(agent.id, \"adhoc\")\nagent_admin_store.enable(agent.id)\nPY\nuv run python -m uvicorn fleetent.server:app --host 127.0.0.1 --port ").concat(smokePort, "\n'");
export default defineConfig({
    testDir: './e2e',
    testMatch: /agents-hosted\.spec\.ts/,
    use: {
        baseURL: "http://127.0.0.1:".concat(smokePort),
        trace: 'retain-on-failure',
    },
    webServer: {
        command: webServerCommand,
        cwd: repoRoot,
        reuseExistingServer: false,
        url: "http://127.0.0.1:".concat(smokePort, "/health"),
    },
});
