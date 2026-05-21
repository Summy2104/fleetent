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

## Testing Conventions

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

Feature development follows OpenSpec spec-driven flow:

```
/opsx:propose "feature-name"   # create proposal + spec + design + tasks
/opsx:apply                    # implement the current change
/opsx:archive                  # archive completed change
```

Changes live in `openspec/changes/`. Propose → refine spec → apply → archive.

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
