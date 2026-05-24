# Slack/Telegram MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend mini-agent into a production-ready Slack + Telegram IM service with session persistence, sub-agent parallelism, two-level permission gates, microsandbox tool execution, and MCP integration.

**Architecture:** Modular monolith — new modules added alongside existing agent_loop/tool_registry/memory_layer. IM adapters normalize messages to a unified format then route through session_mgr → agent_loop. Permission gate sits inside tool_registry.dispatch(). MCP tools register transparently at startup.

**Tech Stack:** Python 3.12, FastAPI, slack-bolt, python-telegram-bot, microsandbox, pydantic-settings, structlog, alembic, SQLite

---

## 1. Foundation: Dependencies + Config + Logging

- [ ] 1.1 Add new dependencies to `pyproject.toml`: `slack-bolt`, `python-telegram-bot>=21`, `microsandbox`, `pydantic-settings`, `structlog`, `alembic`, `mcp`
- [ ] 1.2 Run `uv sync` and verify imports work for all new packages
- [ ] 1.3 Create `src/mini_agent/config.py` — `Settings` class via pydantic-settings, loading from env vars + `config/settings.yaml`. Fields: `anthropic_api_key`, `slack_bot_token`, `slack_app_token`, `telegram_bot_token`, `microsandbox_url` (default `http://host.docker.internal:7777`), `permission_gate_medium_timeout_seconds` (default 300), `permission_gate_high_timeout_seconds` (default 3600)
- [ ] 1.4 Write tests for `config.py`: verify env var overrides yaml default, verify missing required key raises at startup
- [ ] 1.5 Replace `print()`/`logging` calls in existing modules with `structlog.get_logger()` — configure structlog in `server.py` lifespan with JSON renderer in production, console renderer in dev (controlled by `LOG_FORMAT` env var)
- [ ] 1.6 Create `config/settings.yaml.example` and `config/mcp.yaml.example` with documented fields; add `config/*.yaml` and `.env*` to `.gitignore`
- [ ] 1.7 Commit: `feat: add config management (pydantic-settings) and structlog`

## 2. Database Migration (Alembic)

- [ ] 2.1 Run `alembic init migrations` in project root; configure `migrations/env.py` to use `data/users.db` path from `Settings`
- [ ] 2.2 Create `migrations/versions/001_add_im_tables.py` — upgrade adds tables: `im_users`, `agents`, `user_agents`, `approvals`; downgrade drops them. Use exact schema from design.md §5.1
- [ ] 2.3 Write test: apply migration on a fresh in-memory SQLite, verify all 4 tables exist with correct columns; verify downgrade removes them
- [ ] 2.4 Test upgrade on a DB that already has the `users` table (legacy `_init_db` path) — migration must not fail
- [ ] 2.5 Commit: `feat: add alembic migrations for im_users, agents, user_agents, approvals`

## 3. Data Layer: New Stores

- [ ] 3.1 Create `src/mini_agent/im_user_store.py` — `get_or_create(platform, platform_user_id) -> User`: looks up `im_users` join `users`; if not found, inserts new `users` row + `im_users` row atomically; returns `User`
- [ ] 3.2 Write tests for `im_user_store`: first call creates user, second call returns same user_id, two platforms with same external id map to different users
- [ ] 3.3 Create `src/mini_agent/agent_store.py` — `create_agent(name, system_prompt, allowed_tools)`, `get_by_name(name) -> Agent | None`, `get_agent_for_user(user_id) -> Agent | None`, `assign_user(user_id, agent_id)`. `Agent` dataclass: `id, name, system_prompt, allowed_tools: list[str]`
- [ ] 3.4 Write tests for `agent_store`: create, get by name, assign user, get agent for user; verify duplicate name raises
- [ ] 3.5 Add `get_or_create_im_user(platform, platform_user_id) -> User` to `user_store.py` as thin wrapper around `im_user_store.get_or_create()`
- [ ] 3.6 Commit: `feat: add im_user_store and agent_store`

## 4. Tool Registry: Access Control

- [ ] 4.1 Modify `tool_registry.dispatch(tool_name, args)` → `tool_registry.dispatch(tool_name, args, agent_id: str | None = None)`. When `agent_id` is provided, load agent's `allowed_tools` from `agent_store` and check `tool_name` matches (exact or glob `fnmatch`). Raise `PermissionError(f"Tool '{tool_name}' not in agent allowed_tools")` if not matched
- [ ] 4.2 Write tests: tool in allowed_tools passes, tool not in allowed_tools raises PermissionError, wildcard `github__*` matches `github__create_issue`, `agent_id=None` skips check (backwards compat)
- [ ] 4.3 Create `src/mini_agent/agent_policy.py` — `check_tool_access(tool_name: str, allowed_tools: list[str]) -> bool` using `fnmatch.fnmatch` for wildcard support
- [ ] 4.4 Commit: `feat: add access control to tool_registry.dispatch()`

## 5. MCP Client

- [ ] 5.1 Create `src/mini_agent/mcp_client.py` — `McpServerConfig` dataclass (`id, url, auth_type, api_key_env`); `register_all(servers: list[McpServerConfig])` — for each server, connect via MCP HTTP/SSE transport, call `tools/list`, register each tool into `tool_registry` with name `{server.id}__{tool.name}` and a handler that calls `call_tool`; `call_tool(server_id, tool_name, args) -> Any`
- [ ] 5.2 Write tests with a mock MCP server (monkeypatch transport): `register_all` registers tools with correct names, `call_tool` routes to correct server, unreachable server logs warning and continues
- [ ] 5.3 Write test: tool name `linear` + `create_ticket` → registered as `linear__create_ticket`
- [ ] 5.4 Load MCP server configs from `config/mcp.yaml` in `config.py` (`mcp_servers: list[McpServerConfig]`)
- [ ] 5.5 Commit: `feat: implement mcp_client with startup tool registration`

## 6. Sandbox Client

- [ ] 6.1 Create `src/mini_agent/sandbox_client.py` — async HTTP client (httpx). Methods: `create_workspace(session_id: str)`, `exec(session_id: str, command: str) -> ExecResult`, `destroy_workspace(session_id: str)`. `ExecResult` dataclass: `stdout, stderr, exit_code`. Base URL from `Settings.microsandbox_url`
- [ ] 6.2 Write tests with a mock httpx responder: `create_workspace` calls `POST /workspace`, `exec` calls `POST /workspace/{id}/exec`, `destroy_workspace` calls `DELETE /workspace/{id}`
- [ ] 6.3 Write test: `exec` with non-zero exit_code returns `ExecResult` without raising (caller decides on error handling)
- [ ] 6.4 Register `shell` as a built-in tool in `tools.py` that calls `sandbox_client.exec(session_id, command)` — `session_id` passed via tool execution context (add `context: ToolContext` to dispatch signature, containing `session_id`)
- [ ] 6.5 Commit: `feat: implement sandbox_client for microsandbox MicroVM integration`

## 7. Session Persistence

- [ ] 7.1 Create `src/mini_agent/session_mgr.py` — `SessionManager` with `load(session_id) -> list[dict]` (reads `data/sessions/{session_id}.json`, returns `[]` if not found) and `save(session_id, messages: list[dict])` (atomic write via temp file + rename). Per-session `asyncio.Lock` stored in a dict, keyed by `session_id`
- [ ] 7.2 Write tests: load non-existent returns `[]`, save+load round-trips, concurrent saves for same session serialize (use `asyncio.gather` with two tasks writing different content, verify no corruption), two different sessions can load/save concurrently without blocking each other
- [ ] 7.3 Write test for session lock: acquire lock for session A does not block session B
- [ ] 7.4 Commit: `feat: implement session_mgr with JSON persistence and per-session locking`

## 8. Permission Gate

- [ ] 8.1 Create `src/mini_agent/permission_gate.py` — `PermissionGate` with `request_approval(approval_id, risk_level, tool_name, tool_args, requester_user_id, reply_func) -> Literal["approved", "rejected", "timeout"]`. Writes `approvals` table row, creates `asyncio.Event`, calls `reply_func` with IM message + buttons. Uses `asyncio.wait_for` with timeout from `Settings`. On timeout, updates `approvals` to `status=timeout`
- [ ] 8.2 `resolve(approval_id, decision: Literal["approved", "rejected"], approver_user_id)` — updates `approvals` table, calls `event.set()`
- [ ] 8.3 Write tests: mock `reply_func` + mock event — approve path returns `"approved"`, reject path returns `"rejected"`, timeout path returns `"timeout"` after short timeout (use `Settings` override to 0.1s in tests), approvals table updated correctly in each case
- [ ] 8.4 Integrate permission_gate into `tool_registry.dispatch()`: after access control check, if tool has `risk_level` of `"medium"` or `"high"`, call `permission_gate.request_approval()` and block; proceed on `"approved"`, raise on `"rejected"` / `"timeout"`
- [ ] 8.5 Write integration test: dispatch a `risk_level="medium"` tool, mock `permission_gate.request_approval` to return `"approved"` → tool executes; mock to return `"rejected"` → `PermissionError`
- [ ] 8.6 Commit: `feat: implement permission_gate with asyncio.Event approval flow`

## 9. Sub-Agent

- [ ] 9.1 Create `src/mini_agent/sub_agent.py` — `SubAgentExecutor` with `run(tasks: list[dict], parent_user_id, parent_agent_id, parent_session_id) -> list[SubAgentResult]`. Calls `asyncio.gather(*[agent_loop.run(messages=[...], user_id=parent_user_id, agent_id=parent_agent_id, is_sub_agent=True) for t in tasks])`. `SubAgentResult`: `name, result, error`
- [ ] 9.2 Modify `agent_loop.run()` to accept `is_sub_agent: bool = False`. When `True`, prevent registration of the `sub_agent` tool (prevent nesting beyond depth 1)
- [ ] 9.3 Register `sub_agent` as a tool in `tools.py` (disabled when `is_sub_agent=True`): tool name `sub_agent`, args: `tasks: list[{name: str, prompt: str}]`
- [ ] 9.4 Write tests: two tasks run concurrently (verify via timing or mock), child can't spawn sub-agent (returns error), partial failure returns error for failed task + result for succeeded task, eval trace contains `parent_session_id`
- [ ] 9.5 Commit: `feat: implement sub_agent with asyncio.gather parallelism`

## 10. IM Gateway

- [ ] 10.1 Create `src/mini_agent/im_gateway/normalizer.py` — `NormalizedMessage` dataclass: `platform, session_id, user_id, text, attachments, reply_func`; `route(msg: NormalizedMessage, session_mgr, agent_loop, sandbox_client)` — runs the full pipeline: `session_mgr.load → agent_loop.run → session_mgr.save → msg.reply_func(response)`
- [ ] 10.2 Write tests for `route()`: mock all dependencies, verify session is loaded before agent, saved after agent, reply sent with agent output
- [ ] 10.3 Create `src/mini_agent/im_gateway/slack.py` — `SlackAdapter` using `slack-bolt` App with Socket Mode. Handle `message` events. DM → `session_id="user:{slack_user_id}"`. Thread reply → `session_id="thread:{thread_ts}"`. No-thread channel message → bot replies in new thread, `session_id="thread:{new_ts}"`. `reply_func` = `say(text, thread_ts=...)`
- [ ] 10.4 Write tests for Slack adapter: mock `slack-bolt` app event, verify correct `session_id` derivation for DM / thread / channel-no-thread cases
- [ ] 10.5 Create `src/mini_agent/im_gateway/telegram.py` — `TelegramAdapter` using `python-telegram-bot` with polling. Private chat → `session_id="user:{chat_id}"`. Group reply → `session_id="thread:{reply_to_message_id}"`. Group non-reply → `session_id="user:{from_id}"` (DM fallback). `reply_func` = `context.bot.send_message`
- [ ] 10.6 Write tests for Telegram adapter: mock update objects, verify correct `session_id` for private/group/reply cases
- [ ] 10.7 Commit: `feat: implement IM gateway with Slack + Telegram adapters`

## 11. Eval Logger: IM Fields

- [ ] 11.1 Modify `eval_logger.py` — add optional fields to the trace entry: `platform: str | None`, `channel_id: str | None`, `message_id: str | None`, `thread_id: str | None`, `session_id: str | None`
- [ ] 11.2 Pass `session_id` and IM metadata through `agent_loop.run()` → `eval_logger.log()` when available
- [ ] 11.3 Write test: run with IM metadata → trace JSONL contains new fields; run without → fields absent (not null-polluting old traces)
- [ ] 11.4 Commit: `feat: extend eval_logger with IM channel metadata fields`

## 12. Server Wiring

- [ ] 12.1 Modify `server.py` lifespan: on startup, call `alembic upgrade head` (programmatically), then `mcp_client.register_all(settings.mcp_servers)`, start Slack/Telegram adapters as background asyncio tasks if tokens configured
- [ ] 12.2 Add `GET /health` response body with: `{"status": "ok", "adapters": {"slack": bool, "telegram": bool}, "mcp_servers": [...]}`
- [ ] 12.3 Write test: mock mcp_client and adapters, verify lifespan starts them, health endpoint reflects adapter status
- [ ] 12.4 Commit: `feat: wire mcp_client startup and IM adapters into server lifespan`

## 13. Docker Packaging

- [ ] 13.1 Create `Dockerfile`: Python 3.12-slim base, `uv sync --no-dev`, copy src, expose port 8000, CMD `uvicorn mini_agent.server:app`
- [ ] 13.2 Create `docker-compose.yml`: `mini-agent` service with `env_file: .env.production`, `extra_hosts: ["host.docker.internal:host-gateway"]`, `volumes: [./data:/app/data, ./config:/app/config]`
- [ ] 13.3 Create `.env.example` with all required env vars (no values, comments explaining each)
- [ ] 13.4 Test: `docker build -t mini-agent .` succeeds; `docker run --env-file .env.test mini-agent python -c "from mini_agent.config import Settings; Settings()"` exits 0
- [ ] 13.5 Commit: `feat: add Dockerfile and docker-compose for on-premises deployment`

## 14. Integration Test: Full Message Flow

- [ ] 14.1 Write end-to-end integration test: mock Slack event → normalizer → session_mgr (tmp_path) → agent_loop (mock LLM) → session saved → reply_func called with agent output. Verify session file written, reply called once, eval trace contains session_id
- [ ] 14.2 Write test: medium-risk tool in allowed_tools → approval mocked to "approved" → tool executes, approvals table shows `approved`
- [ ] 14.3 Write test: tool NOT in allowed_tools → PermissionError before approval gate, approvals table has no row
- [ ] 14.4 Run full test suite: `uv run pytest` — all tests pass, coverage ≥ 80% on new modules
- [ ] 14.5 Commit: `test: add integration tests for full IM message flow`
