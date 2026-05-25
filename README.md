# fleetent

Lean agent platform in Python. No AI framework — just a FastAPI HTTP server, a tool-calling loop, and clean module boundaries.

Built to run as a multi-user IM-native agent service (Slack, Telegram) with support for MCP tool servers, sub-agents, cross-session memory, and human-in-the-loop approval.

## Quick Start

```bash
# Prerequisites: Python 3.12+, uv, ANTHROPIC_API_KEY
git clone https://github.com/raw34/fleetent.git
cd fleetent
uv sync
cp config/settings.yaml.example config/settings.yaml   # optional
export ANTHROPIC_API_KEY=sk-ant-...
```

**CLI mode (single user, no auth):**

```bash
uv run fleetent "What time is it, and what is 123 * 456?"
```

**HTTP server mode (multi-user, Bearer auth):**

```bash
# Start the server
uvicorn fleetent.server:app --reload

# Create a user and get an API key
uv run fleetent-admin create-user --name "Alice"
# → api_key: ma-abc123...

# Chat via SSE
curl -s http://localhost:8000/chat \
  -H "Authorization: Bearer ma-abc123..." \
  -H "Content-Type: application/json" \
  -d '{"message": "What is 7 * 8?"}' | grep "^data:"
```

## Architecture

```
                        ┌─────────────────────────────────────────┐
                        │              HTTP / IM                   │
                        │  POST /chat (SSE)  Slack  Telegram       │
                        └────────────────┬────────────────────────┘
                                         │ NormalizedMessage
                                         ▼
                              ┌──────────────────────┐
                              │   agent_loop.run()   │  ← the while loop
                              │                      │
                              │  load_memories()     │  cross-session facts
                              │  maybe_compress()    │  token management
                              │  match_skill()       │  SKILL.md injection
                              └────────┬─────────────┘
                                       │
                              ┌────────▼─────────────┐
                              │   model_router        │  OpenAI-compatible
                              │   (Anthropic default) │  swap by editing ROUTES
                              └────────┬─────────────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    │ finish_reason    │                   │
                    │ == "tool_calls"  │                   │
                    ▼                  │                   │
         tool_registry.dispatch()     │                   │
         ├── built-in tools           │                   │
         ├── MCP tools (server__name) │                   │
         └── sub_agent (parallel)     │                   │
                    │                 │                   │
                    └─────────────────┘                   │
                              finish_reason == "stop"     │
                                       │                  │
                              log_run() + extract_and_save()
                                       │
                                    reply
```

## Modules

| Module | Role |
|--------|------|
| `agent_loop.py` | Tool-calling while loop. `run()` returns text; `run_stream()` yields SSE events. |
| `model_router.py` | Maps task types to OpenAI-compatible endpoints. Edit `ROUTES` to switch providers. |
| `tool_registry.py` | `@tool` decorator, JSON Schema generation, dispatch. |
| `tools.py` | Built-in tools: `calculate`, `get_current_time`, `read_file`. |
| `skill_registry.py` | Scans `skills/` for `SKILL.md` files; injects matching ones into the system prompt. |
| `context_mgr.py` | Compresses old history with a haiku summary when token budget is exceeded. |
| `memory_layer.py` | Extracts facts after each run (haiku) → JSONL → injects into next session. |
| `session_mgr.py` | JSON session persistence per user; atomic writes; per-session asyncio lock. |
| `user_store.py` | SQLite user and API key management. |
| `agent_store.py` | SQLite CRUD for named agent definitions and user-agent assignments. |
| `im_user_store.py` | Maps `(platform, platform_user_id)` → internal User. Auto-creates on first message. |
| `im_gateway/normalizer.py` | `NormalizedMessage` dataclass; `route()` pipeline called by all IM adapters. |
| `im_gateway/slack.py` | Slack Socket Mode adapter (slack-bolt). |
| `im_gateway/telegram.py` | Telegram polling adapter (python-telegram-bot). |
| `mcp_client.py` | Connects to MCP HTTP/SSE tool servers; registers tools as `{server}__{tool}`. |
| `sub_agent.py` | Runs tasks in parallel via `asyncio.gather`; max depth 1 (no nesting). |
| `permission_gate.py` | asyncio.Event-based human approval gate for medium/high-risk tool calls. |
| `sandbox_client.py` | httpx client for microsandbox MicroVM workspace/exec. |
| `agent_policy.py` | fnmatch-based tool access control (`allowed_tools` per agent). |
| `server.py` | FastAPI: `POST /chat` (SSE), `GET /health`, Bearer auth. |
| `admin.py` | CLI: `create-user`, `list-users`, `rotate-key`. |
| `config.py` | pydantic-settings; loads `.env` + `config/settings.yaml`. |
| `eval_logger.py` | Append-only JSONL trace log at `data/traces.jsonl`. |

## HTTP API

### Authentication

All `/chat` requests require a Bearer token issued by the admin CLI:

```bash
uv run fleetent-admin create-user --name "Alice"
# api_key: ma-<64 hex chars>
```

```
Authorization: Bearer ma-<64hex>
```

### POST /chat

Streams a Server-Sent Events response:

```bash
curl -s http://localhost:8000/chat \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the current time?"}'
```

**Event types:**

```
data: {"type": "text_delta", "content": "The current"}
data: {"type": "tool_call",  "name": "get_current_time", "args": {}}
data: {"type": "tool_result","name": "get_current_time", "content": "2026-05-24T10:00:00Z"}
data: {"type": "text_delta", "content": " time is 10:00 UTC."}
data: {"type": "done",       "content": "The current time is 10:00 UTC."}
```

### GET /health

```json
{"status": "ok", "adapters": {"slack": false, "telegram": false}}
```

## Adding Tools

```python
# src/fleetent/tools.py  (or any file imported at startup)
from fleetent.tool_registry import tool

@tool
def search_database(query: str, limit: int = 10) -> str:
    """Search the internal database. Returns matching records as JSON."""
    ...
    return json.dumps(results)
```

The `@tool` decorator auto-generates the OpenAI function-calling JSON Schema from type annotations and the docstring. Tools are available to all agents unless restricted by `agent_policy`.

## Skills

Drop a `SKILL.md` into `skills/<skill-name>/SKILL.md`. The registry scans for skills at startup and injects matching ones into the system prompt when the user's message triggers a keyword match.

```
skills/
  summarize-doc/
    SKILL.md     ← injected when user asks to summarize something
```

## IM Adapters

### Slack

```bash
export SLACK_BOT_TOKEN=xoxb-...
export SLACK_APP_TOKEN=xapp-...
uvicorn fleetent.server:app --reload
```

The server starts the Slack Socket Mode handler as a background task on startup. Each Slack user is auto-mapped to an internal user on first message.

### Telegram

```bash
export TELEGRAM_BOT_TOKEN=...
uvicorn fleetent.server:app --reload
```

Uses polling mode. The bot handles private chats and group replies. Session IDs are scoped to user (`user:{id}`) or thread (`thread:{message_id}`).

## MCP Integration

Connect any MCP-compatible HTTP tool server by creating `config/mcp.yaml`:

```yaml
servers:
  - id: linear
    url: http://localhost:3000
    auth_type: api_key
    api_key_env: LINEAR_API_KEY

  - id: github
    url: http://localhost:3001
    auth_type: none
```

Tools are registered at server startup as `linear__create_issue`, `github__list_prs`, etc. The double underscore namespace prevents collisions with built-in tools.

## Sub-agents

The `sub_agent` tool lets the main agent delegate tasks to parallel child agents:

```
User: "Summarize the last 3 Jira tickets and draft a Slack update for each."

Agent → sub_agent({tasks: [
  {name: "ticket_1", prompt: "Summarize PROJ-101"},
  {name: "ticket_2", prompt: "Summarize PROJ-102"},
  {name: "ticket_3", prompt: "Summarize PROJ-103"}
]})
```

Sub-agents run concurrently via `asyncio.gather`. Nesting is blocked at depth 1 — sub-agents cannot spawn further sub-agents.

## Configuration

**Environment variables (required):**

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Default LLM route (Anthropic) |

**Environment variables (optional):**

| Variable | Description |
|----------|-------------|
| `SLACK_BOT_TOKEN` | Enables Slack adapter |
| `SLACK_APP_TOKEN` | Required alongside `SLACK_BOT_TOKEN` |
| `TELEGRAM_BOT_TOKEN` | Enables Telegram adapter |
| `MICROSANDBOX_URL` | Sandbox MicroVM URL (default: `http://host.docker.internal:7777`) |
| `MINI_AGENT_SKILLS_DIR` | Override skills directory (default: `./skills`) |

**Switching LLM providers:**

Edit `ROUTES` in `src/fleetent/model_router.py`:

```python
ROUTES = {
    "default": RouteConfig(
        base_url="https://api.openai.com/v1/",
        model="gpt-4o-mini",
        api_key_env="OPENAI_API_KEY",
        max_tokens=4096,
    ),
}
```

The agent loop, tool registry, and memory layer are provider-agnostic — only `model_router.py` knows about the LLM endpoint.

## Development

```bash
uv run pytest                    # run all tests (151 tests, ~4s)
uv run pytest -x -q              # fail-fast
uv run pytest --cov=fleetent   # with coverage (89%)
uv run ruff check src tests      # lint
uv run mypy src                  # type-check

# Smoke tests against a live server
uvicorn fleetent.server:app &
uv run python tests/smoke/smoke.py
```

## Internals

Per-module deep dives in [`docs/internals/`](docs/internals/):

| Doc | Covers |
|-----|--------|
| [agent_loop.md](docs/internals/agent_loop.md) | Loop structure, run/run_stream/run_sync differences, is_sub_agent filtering, streaming tool_call accumulation |
| [tool_registry.md](docs/internals/tool_registry.md) | @tool decorator, dispatch, MCP naming convention, access control |
| [memory_layer.md](docs/internals/memory_layer.md) | Extract/inject flow, per-user JSONL, haiku extraction, known caveats |
| [model_router.md](docs/internals/model_router.md) | Route config, sync vs async clients, provider switching |
| [eval_logger.md](docs/internals/eval_logger.md) | log_run vs log, JSONL format, _serialize duck typing |
| [context_mgr.md](docs/internals/context_mgr.md) | Token compression, identity-check gotcha in _keep_tail |
| [session_mgr.md](docs/internals/session_mgr.md) | Atomic writes, per-session asyncio.Lock, test isolation |
| [sub_agent.md](docs/internals/sub_agent.md) | asyncio.gather parallelism, max depth 1, partial failure handling |
| [mcp_client.md](docs/internals/mcp_client.md) | Registration flow, double-underscore naming, auth, runtime dispatch |
| [im_gateway.md](docs/internals/im_gateway.md) | NormalizedMessage, route() pipeline, session_id derivation per platform |

## License

Apache 2.0. Copyright 2026 Randy Chang.
