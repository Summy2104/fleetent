# mini-agent

Lean agent platform — Python, FastAPI, no frameworks.
Foundation for a multi-user IM-native agent service (Slack/Telegram/WhatsApp).

## Commands

```bash
uv sync                          # install deps
uv run pytest                    # run tests (48, ~0.5s)
uv run pytest -x -q              # fail-fast
uv run ruff check src tests      # lint
uv run mypy src                  # type-check
uv run mini-agent "hello"        # CLI
uv run mini-agent-admin create-user --name "Alice"  # user mgmt
uvicorn mini_agent.server:app --reload  # HTTP server (port 8000)
```

## Architecture

Modular monolith. Each module has one responsibility and a clean interface.

```
src/mini_agent/
  agent_loop.py      ← while tool-use loop; run() + run_stream()
  model_router.py    ← maps task type → provider config (OpenAI-compatible)
  tool_registry.py   ← @tool decorator, schema building, dispatch
  tools.py           ← built-in tools (register on import as side-effect)
  skill_registry.py  ← scans skills/, progressive SKILL.md injection
  context_mgr.py     ← in-session token compression, identity-based keep_tail
  memory_layer.py    ← cross-session facts: extract via haiku → JSONL → inject
  user_store.py      ← SQLite user/api-key management (data/users.db)
  eval_logger.py     ← append-only JSONL trace log (data/traces.jsonl)
  server.py          ← FastAPI: POST /chat (SSE), GET /health, Bearer auth
  admin.py           ← CLI: create-user, list-users, rotate-key
```

## Data Directory

```
data/
  users.db                        # SQLite — gitignored
  users/{user_id}/memories.jsonl  # per-user memories — gitignored
  traces.jsonl                    # eval traces — gitignored
```

Tests use `tmp_path + monkeypatch` to redirect all data paths — never touch `data/` in tests.

## Testing Approach

Tests are written before production code — see OpenSpec Workflow below for the hard gate.

Isolation patterns:
- `monkeypatch.setattr(module, "DB_PATH", tmp_path / "x.db")` — isolate SQLite
- `monkeypatch.setattr(memory_layer, "_mem_path", ...)` — isolate memory files
- `patch("mini_agent.memory_layer.get_client_and_config", ...)` — mock LLM calls
- All async tests auto-collected via `asyncio_mode = auto` in pytest.ini

## Environment Variables

```
ANTHROPIC_API_KEY      # required for default route
MINI_AGENT_SKILLS_DIR  # override skills/ directory (default: ./skills)
```

## OpenSpec Workflow

本项目使用 OpenSpec 流进行功能开发（见用户级 CLAUDE.md 的完整流程定义）。

**1. opsx:propose** — 定义「做什么」

- 写 proposal.md、specs/、design.md（可选）、tasks.md
- tasks.md 中**测试任务必须在对应实现任务之前**：
  ```
  - [ ] 3.1 Write failing tests for X: ...
  - [ ] 3.2 Implement X to pass tests
  ```
- 所有 artifact review 通过后才能进入实施

**2. 建 worktree + 功能分支**

**3. opsx:apply** — 每个 task 强制 TDD（hard gate）

- 先写测试，运行 `uv run pytest -x -q`，**必须看到红**，不红不能继续
- 再写实现，运行 `uv run pytest -x -q`，**必须看到绿**，不绿不能继续
- 可选 refactor，确保仍然绿
- 完成后将该 task 标记为 `[x]`
- 跳过任何一步 = 违反流程

**4. merge / PR，清理 worktree**

**5. opsx:archive** — 所有 checkbox 为 `[x]` 后归档，同步 specs

## Code Style

- Line length: 100 (ruff)
- Type checking: mypy strict
- No comments unless the WHY is non-obvious

## Gotchas

- `tools.py` registers tools as side-effect on import — `agent_loop.py` imports it at the top
- `skill_registry.scan()` runs at server startup (FastAPI lifespan), not per-request; runs per-call in CLI `run()`
- `context_mgr._keep_tail()` uses identity check (`m is tail[0]`), not equality — dict equality fails for identical-content messages
- Bearer token format: `Authorization: Bearer ma-<64hex>` — `ma-` prefix distinguishes service keys from model API keys
- `model_router.get_async_client_and_config()` creates a new client each call — intentional, clients are stateless and cheap
