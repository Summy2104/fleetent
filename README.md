# fleetent

fleetent is a lean, self-hosted agent platform for enterprise IM and internal tools. It is built with Python and FastAPI, avoids heavyweight AI frameworks, and keeps data inside the deployment boundary.

Core capabilities include:

- multi-user HTTP, Slack and Telegram entry points;
- OpenAI-compatible model routing with provider fallback;
- tool calling, MCP tool servers and sub-agents;
- user memory, shared memory, long-term context and knowledge base retrieval;
- human approval gates for risky tool calls;
- observability traces, usage summaries, diagnostics and pilot verification reports;
- SQLite-first local runtime with Alembic-managed schema lifecycle.

## Quick Start

```bash
# Prerequisites: Python 3.12+, uv and an LLM provider API key.
git clone <repo-url>
cd fleetent
uv sync
cp config/settings.yaml.example config/settings.yaml
export ANTHROPIC_API_KEY=sk-ant-...
```

Run a single CLI request:

```bash
uv run fleetent "What time is it, and what is 123 * 456?"
```

Start the HTTP server:

```bash
uv run uvicorn fleetent.server:app --reload --port 8765
```

Create a user and call `/chat`:

```bash
uv run fleetent-admin create-user --name "Alice"
# api_key: ma-<64 hex chars>

curl -s http://localhost:8765/chat \
  -H "Authorization: Bearer ma-<64hex>" \
  -H "Content-Type: application/json" \
  -d '{"message": "What is 7 * 8?"}' | grep "^data:"
```

Run the interactive terminal UI:

```bash
uv run fleetent-tui --url ws://127.0.0.1:8765/ws --token ma-<64hex>
```

## Architecture

```text
HTTP / IM / TUI
      |
      v
NormalizedMessage / WebSocket request
      |
      v
agent_loop.run() / run_stream()
      |
      +--> long-term context, memory, knowledge base
      +--> model_router
      +--> tool_registry
              |
              +--> built-in tools
              +--> MCP tools
              +--> sub-agents
              +--> sandbox tools
      |
      v
observability traces, usage, diagnostics, session persistence
```

The codebase is moving from legacy flat modules toward a modular monolith. New code should prefer package boundaries under `src/fleetent/`:

| Package | Role |
| --- | --- |
| `runtime` / flat runtime modules | Agent loop, termination, cancellation, budgets and session runtime behavior. |
| `governance` | Approval gates, quotas, audit log, blocklist and agent policy. |
| `platform` | Admin APIs, user management, agent management, connector management and console surfaces. |
| `im_gateway` | Slack and Telegram normalization and routing. |
| `integrations` | MCP, sandbox and external integration boundaries. |
| `intelligence` | Memory, shared memory, long-term context, reflection, vector store and knowledge base. |
| `observability` | Trace storage, usage/performance summaries, diagnostics and verification reports. |
| `tui` | Interactive terminal client and WebSocket dispatch protocol. |

Cross-package calls should use public APIs. Avoid importing internal implementation details from migrated packages.

## Configuration

Settings are loaded from environment variables and `config/settings.yaml`.

Required for normal LLM-backed operation:

| Variable | Description |
| --- | --- |
| `ANTHROPIC_API_KEY` | Default Anthropic-compatible route credential. |

Common optional variables:

| Variable | Description |
| --- | --- |
| `SLACK_BOT_TOKEN` | Enables Slack adapter. |
| `SLACK_APP_TOKEN` | Required alongside `SLACK_BOT_TOKEN` for Slack Socket Mode. |
| `TELEGRAM_BOT_TOKEN` | Enables Telegram adapter. |
| `MICROSANDBOX_URL` | Sandbox service URL. |
| `MINI_AGENT_SKILLS_DIR` | Override skill directory. |

Model routes are configured in `settings.yaml` and `model_router.py` using OpenAI-compatible endpoints. Do not commit real API keys, IM tokens, OAuth credentials or local `.env` files.

## HTTP API

### Authentication

`/chat` requires a Bearer token issued by the admin CLI:

```text
Authorization: Bearer ma-<64hex>
```

### POST /chat

Streams Server-Sent Events:

```bash
curl -s http://localhost:8765/chat \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the current time?"}'
```

Example event types:

```text
data: {"type": "text_delta", "content": "The current"}
data: {"type": "tool_call", "name": "get_current_time", "args": {}}
data: {"type": "tool_result", "name": "get_current_time", "content": "..."}
data: {"type": "done", "content": "The current time is ..."}
```

### GET /health

```json
{"status": "ok", "adapters": {"slack": false, "telegram": false}}
```

## Tools and MCP

Built-in tools are registered with `@tool`:

```python
from fleetent.tool_registry import tool


@tool
def search_database(query: str, limit: int = 10) -> str:
    """Search the internal database. Returns matching records as JSON."""
    ...
```

MCP-compatible tool servers can be configured in `config/mcp.yaml`:

```yaml
servers:
  - id: internal_tools
    url: http://localhost:3000
    auth_type: api_key
    api_key_env: INTERNAL_TOOLS_API_KEY
```

MCP tools are registered as `{server_id}__{tool_name}` to avoid name collisions.

## Skills

Skills live under `skills/<skill-name>/SKILL.md`. The registry scans them at startup and the agent can read matching skill instructions on demand.

```text
skills/
  summarize-doc/
    SKILL.md
```

## Development

Install dependencies:

```bash
uv sync
```

Run tests:

```bash
uv run pytest
uv run pytest -x -q
uv run pytest tests/unit
uv run pytest tests/integration
uv run pytest tests/e2e
uv run pytest tests/evaluation
```

Run quality checks:

```bash
uv run ruff format src tests
uv run ruff check src tests
uv run mypy src
PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py
```

Generate pilot verification evidence when the verification suite is available:

```bash
uv run python scripts/generate_pilot_verification_report.py
```

## Documentation

Primary docs:

| Doc | Purpose |
| --- | --- |
| `docs/architecture.md` | Architecture overview and capability index. |
| `docs/capabilities/` | Capability-level design and status documents. |
| `docs/deployment/` | Pilot install, runbook, acceptance and secrets guidance. |
| `openspec/` | Spec-driven proposals, tasks and archived changes. |

## License

Apache 2.0. See the project license metadata for details.
