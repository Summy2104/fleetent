# Superpowers Extension Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend mini-agent from a single-user CLI tool into a multi-user HTTP agent service with context management, skill loading, and SSE streaming.

**Architecture:** Add 5 new modules (context_mgr, skill_registry, user_store, server, admin) and extend 2 existing ones (memory_layer for user_id scoping, agent_loop to wire everything together + add async streaming). MCP and OAuth permissions are Phase 2 — not in this plan.

**Tech Stack:** Python 3.12, FastAPI, SQLite (stdlib), pytest, uvicorn, httpx (TestClient)

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `src/mini_agent/context_mgr.py` | Create | Token estimation + in-session message compression |
| `src/mini_agent/skill_registry.py` | Create | Scan skills/, keyword match, load SKILL.md |
| `src/mini_agent/user_store.py` | Create | SQLite CRUD for users + API keys |
| `src/mini_agent/server.py` | Create | FastAPI app: POST /chat (SSE), GET /health |
| `src/mini_agent/admin.py` | Create | CLI: create-user, list-users, rotate-key |
| `src/mini_agent/memory_layer.py` | Modify | Add user_id param, scope memories per user |
| `src/mini_agent/model_router.py` | Modify | Add get_async_client_and_config() |
| `src/mini_agent/agent_loop.py` | Modify | Add user_id param, wire context_mgr + skill_registry; add async run_stream() |
| `skills/summarize-doc/SKILL.md` | Create | Sample skill for testing |
| `pyproject.toml` | Modify | Add fastapi, uvicorn, httpx, pytest, pytest-asyncio |
| `tests/test_context_mgr.py` | Create | Tests for token estimation and compress trigger |
| `tests/test_skill_registry.py` | Create | Tests for scan, match, load |
| `tests/test_user_store.py` | Create | Tests for create, get_by_api_key, get_by_id |
| `tests/test_server.py` | Create | Tests for /health and /chat auth |

---

## Task 0: Project Setup

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/__init__.py`
- Create: `skills/summarize-doc/SKILL.md`
- Create: `pytest.ini`

- [ ] **Step 1: Add dependencies to pyproject.toml**

Replace the `[project]` dependencies and dev group:

```toml
[project]
name = "mini-agent"
version = "0.2.0"
description = "Minimal Agent loop in ~300 lines of Python. No framework."
requires-python = ">=3.12"
license = { text = "Apache-2.0" }
dependencies = [
    "openai>=1.50.0",
    "fastapi>=0.115.0",
    "uvicorn>=0.30.0",
]

[project.scripts]
mini-agent = "mini_agent.__main__:main"
mini-agent-admin = "mini_agent.admin:main"

[dependency-groups]
dev = [
    "ruff>=0.6.0",
    "mypy>=1.11.0",
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "httpx>=0.27.0",
]
```

- [ ] **Step 2: Create pytest config**

Create `pytest.ini`:

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

- [ ] **Step 3: Create tests package**

```bash
mkdir -p tests
touch tests/__init__.py
```

- [ ] **Step 4: Create sample skill**

Create `skills/summarize-doc/SKILL.md`:

```markdown
---
name: summarize-doc
description: Summarize documents, articles, or long text. Use when user asks to summarize, tldr, or condense content.
---

## Instructions

When summarizing:
1. Start with a one-sentence TL;DR
2. List 3-5 key points as bullets
3. Keep total length under 200 words unless asked for more
```

- [ ] **Step 5: Sync dependencies**

```bash
uv sync
```

Expected: resolves fastapi, uvicorn, httpx, pytest, pytest-asyncio with no errors.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml pytest.ini tests/__init__.py skills/
git commit -m "chore: add fastapi/pytest deps, test scaffold, sample skill"
```

---

## Task 1: context_mgr.py

**Files:**
- Create: `src/mini_agent/context_mgr.py`
- Create: `tests/test_context_mgr.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_context_mgr.py`:

```python
from mini_agent.context_mgr import DEFAULT_CONFIG, estimate_tokens, maybe_compress


def _make_messages(n: int) -> list[dict]:
    return [
        {"role": "system", "content": "You are helpful."},
        *[
            {"role": "user" if i % 2 == 0 else "assistant", "content": "x" * 500}
            for i in range(n)
        ],
    ]


def test_estimate_tokens_proportional():
    msgs = [{"role": "user", "content": "a" * 400}]
    assert estimate_tokens(msgs) == 100  # 400 chars // 4


def test_no_compress_below_threshold():
    msgs = _make_messages(2)
    result = maybe_compress(msgs)
    assert result is msgs  # same object, no compression


def test_compress_triggers_above_threshold(monkeypatch):
    # Patch _summarize so we don't call the real LLM in tests
    import mini_agent.context_mgr as cm
    monkeypatch.setattr(cm, "_summarize", lambda msgs: "Summary: user asked things.")

    # Build messages big enough to exceed threshold
    big_msgs = [
        {"role": "system", "content": "sys"},
        *[
            {"role": "user" if i % 2 == 0 else "assistant", "content": "x" * 2000}
            for i in range(100)
        ],
    ]
    config = {**DEFAULT_CONFIG, "max_tokens": 10_000, "compress_threshold": 0.5, "keep_recent": 4}
    result = maybe_compress(big_msgs, config=config)

    assert result is not big_msgs  # new list
    roles = [m["role"] for m in result if isinstance(m, dict)]
    assert roles[0] == "system"  # system prompt preserved first
    assert any("Summary" in str(m.get("content", "")) for m in result)  # summary injected
    assert len([m for m in result if m.get("role") != "system"]) <= 5  # summary + keep_recent
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_context_mgr.py -v
```

Expected: `ImportError: No module named 'mini_agent.context_mgr'`

- [ ] **Step 3: Implement context_mgr.py**

Create `src/mini_agent/context_mgr.py`:

```python
"""In-session context compression: summarize old history when token limit approaches."""

from typing import Any

from mini_agent.model_router import get_client_and_config

ContextConfig = dict[str, Any]

DEFAULT_CONFIG: ContextConfig = {
    "max_tokens": 200_000,
    "compress_threshold": 0.8,
    "keep_recent": 10,
}


def estimate_tokens(messages: list[Any]) -> int:
    """Rough token count: 1 token ≈ 4 chars."""
    return sum(len(str(m)) for m in messages) // 4


def maybe_compress(
    messages: list[Any],
    config: ContextConfig = DEFAULT_CONFIG,
) -> list[Any]:
    """If messages exceed threshold, compress and return new list. Otherwise return as-is."""
    threshold = int(config["max_tokens"] * config["compress_threshold"])
    if estimate_tokens(messages) <= threshold:
        return messages

    keep_recent = config["keep_recent"]

    # Separate system prompt from conversation
    system_msgs = [m for m in messages if _role(m) == "system"]
    conv_msgs = [m for m in messages if _role(m) != "system"]

    # Keep complete tool_call/tool_result pairs at tail to avoid LLM errors
    tail = _keep_tail(conv_msgs, keep_recent)
    to_summarize = conv_msgs[: len(conv_msgs) - len(tail)]

    summary_text = _summarize(to_summarize)
    summary_msg: dict[str, str] = {
        "role": "system",
        "content": f"[Earlier conversation summary]\n{summary_text}",
    }

    return [*system_msgs, summary_msg, *tail]


def _summarize(messages: list[Any]) -> str:
    client, cfg = get_client_and_config("memory_extraction")
    text = "\n".join(
        f"{_role(m)}: {_content(m)}"
        for m in messages
        if _role(m) in ("user", "assistant") and _content(m)
    )
    response = client.chat.completions.create(
        model=cfg.model,
        messages=[
            {
                "role": "user",
                "content": (
                    "Summarize this conversation concisely. "
                    "Focus on user goals and completed actions:\n\n" + text
                ),
            }
        ],
        max_tokens=512,
    )
    return response.choices[0].message.content or ""


def _keep_tail(msgs: list[Any], n: int) -> list[Any]:
    """Return last n messages, extended backward to include any incomplete tool pairs."""
    tail = msgs[-n:] if len(msgs) > n else msgs[:]
    # Ensure no orphaned tool_call at the start of tail
    while tail and _role(tail[0]) == "tool":
        idx = msgs.index(tail[0])
        if idx > 0:
            tail = [msgs[idx - 1], *tail]
        else:
            break
    return tail


def _role(msg: Any) -> str:
    if isinstance(msg, dict):
        return str(msg.get("role", ""))
    return str(getattr(msg, "role", ""))


def _content(msg: Any) -> str:
    if isinstance(msg, dict):
        return str(msg.get("content", ""))
    return str(getattr(msg, "content", "") or "")
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_context_mgr.py -v
```

Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/mini_agent/context_mgr.py tests/test_context_mgr.py
git commit -m "feat: add context_mgr for in-session compression"
```

---

## Task 2: skill_registry.py

**Files:**
- Create: `src/mini_agent/skill_registry.py`
- Create: `tests/test_skill_registry.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_skill_registry.py`:

```python
import textwrap
from pathlib import Path

import pytest

import mini_agent.skill_registry as sr


@pytest.fixture(autouse=True)
def reset_registry():
    sr._index.clear()
    yield
    sr._index.clear()


def test_scan_builds_index(tmp_path):
    skill_dir = tmp_path / "skills" / "my-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        textwrap.dedent("""\
            ---
            name: my-skill
            description: Use when user wants to deploy code to production servers.
            ---

            ## Instructions
            Run the deploy script.
        """)
    )
    sr.scan(str(tmp_path / "skills"))
    assert "my-skill" in sr._index
    desc, path = sr._index["my-skill"]
    assert "deploy" in desc.lower()
    assert Path(path).exists()


def test_match_returns_skill_on_keyword(tmp_path):
    skill_dir = tmp_path / "skills" / "deploy"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: deploy\ndescription: Use when user wants to deploy code.\n---\nDeploy it."
    )
    sr.scan(str(tmp_path / "skills"))
    assert sr.match("please deploy my application") == "deploy"


def test_match_returns_none_on_no_match(tmp_path):
    skill_dir = tmp_path / "skills" / "deploy"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: deploy\ndescription: Use when user wants to deploy code.\n---\nDeploy it."
    )
    sr.scan(str(tmp_path / "skills"))
    assert sr.match("what is the weather today?") is None


def test_load_returns_full_content(tmp_path):
    skill_dir = tmp_path / "skills" / "my-skill"
    skill_dir.mkdir(parents=True)
    content = "---\nname: my-skill\ndescription: test skill.\n---\n## Do this."
    (skill_dir / "SKILL.md").write_text(content)
    sr.scan(str(tmp_path / "skills"))
    assert sr.load("my-skill") == content


def test_list_skills_returns_name_and_description(tmp_path):
    for name, desc in [("a", "alpha skill"), ("b", "beta skill")]:
        d = tmp_path / "skills" / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {desc}\n---\nInstructions.")
    sr.scan(str(tmp_path / "skills"))
    skills = sr.list_skills()
    names = [s["name"] for s in skills]
    assert "a" in names and "b" in names
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_skill_registry.py -v
```

Expected: `ImportError: No module named 'mini_agent.skill_registry'`

- [ ] **Step 3: Implement skill_registry.py**

Create `src/mini_agent/skill_registry.py`:

```python
"""Skill registry: scan skills/, match user input, load SKILL.md content."""

from pathlib import Path

# {name: (description, skill_md_path)}
_index: dict[str, tuple[str, str]] = {}

_STOP_WORDS = {"the", "a", "an", "when", "use", "for", "to", "and", "or", "is", "are", "want"}


def scan(skills_dir: str = "skills") -> None:
    """Scan skills directory and build name → (description, path) index."""
    _index.clear()
    base = Path(skills_dir)
    if not base.is_dir():
        return
    for skill_md in base.glob("*/SKILL.md"):
        frontmatter = _parse_frontmatter(skill_md.read_text(encoding="utf-8"))
        name = frontmatter.get("name") or skill_md.parent.name
        description = frontmatter.get("description", "")
        _index[name] = (description, str(skill_md))


def match(user_input: str) -> str | None:
    """Return the first skill name whose description keywords appear in user_input."""
    lowered = user_input.lower()
    for name, (description, _) in _index.items():
        keywords = {
            w.strip(".,!?").lower()
            for w in description.split()
            if len(w) > 4 and w.lower() not in _STOP_WORDS  # noqa: SIM118
        }
        if any(kw in lowered for kw in keywords):
            return name
    return None


def load(name: str) -> str:
    """Return full SKILL.md content for the named skill."""
    _, path = _index[name]
    return Path(path).read_text(encoding="utf-8")


def list_skills() -> list[dict[str, str]]:
    """Return all skills as [{"name": ..., "description": ...}]."""
    return [{"name": name, "description": desc} for name, (desc, _) in _index.items()]


def _parse_frontmatter(content: str) -> dict[str, str]:
    """Extract key: value pairs from YAML frontmatter between --- delimiters."""
    result: dict[str, str] = {}
    if not content.startswith("---"):
        return result
    parts = content.split("---", 2)
    if len(parts) < 3:
        return result
    for line in parts[1].splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            result[key.strip()] = val.strip()
    return result
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_skill_registry.py -v
```

Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/mini_agent/skill_registry.py tests/test_skill_registry.py
git commit -m "feat: add skill_registry for progressive skill loading"
```

---

## Task 3: user_store.py

**Files:**
- Create: `src/mini_agent/user_store.py`
- Create: `tests/test_user_store.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_user_store.py`:

```python
import pytest
from mini_agent import user_store


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(user_store, "DB_PATH", tmp_path / "users.db")


def test_create_user_returns_user():
    user = user_store.create_user("Alice")
    assert user.name == "Alice"
    assert user.api_key.startswith("ma-")
    assert len(user.id) == 36  # uuid4


def test_get_by_api_key_found():
    user = user_store.create_user("Bob")
    found = user_store.get_by_api_key(user.api_key)
    assert found is not None
    assert found.id == user.id


def test_get_by_api_key_not_found():
    assert user_store.get_by_api_key("ma-doesnotexist") is None


def test_get_by_id_found():
    user = user_store.create_user("Carol")
    found = user_store.get_by_id(user.id)
    assert found is not None
    assert found.name == "Carol"


def test_get_by_id_not_found():
    assert user_store.get_by_id("00000000-0000-0000-0000-000000000000") is None


def test_list_users_returns_all():
    user_store.create_user("Dave")
    user_store.create_user("Eve")
    users = user_store.list_users()
    names = [u.name for u in users]
    assert "Dave" in names and "Eve" in names


def test_rotate_key_changes_api_key():
    user = user_store.create_user("Frank")
    old_key = user.api_key
    updated = user_store.rotate_key(user.id)
    assert updated.api_key != old_key
    assert updated.api_key.startswith("ma-")
    assert user_store.get_by_api_key(old_key) is None
    assert user_store.get_by_api_key(updated.api_key) is not None
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_user_store.py -v
```

Expected: `ImportError: No module named 'mini_agent.user_store'`

- [ ] **Step 3: Implement user_store.py**

Create `src/mini_agent/user_store.py`:

```python
"""SQLite-backed user store. Each user has a uuid id and an API key."""

import datetime
import secrets
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path

DB_PATH = Path("data/users.db")


@dataclass
class User:
    id: str
    name: str
    api_key: str
    created_at: str


def create_user(name: str) -> User:
    """Create a new user with a generated uuid and API key."""
    _init_db()
    user = User(
        id=str(uuid.uuid4()),
        name=name,
        api_key=f"ma-{secrets.token_hex(32)}",
        created_at=datetime.datetime.now(datetime.UTC).isoformat(),
    )
    with _conn() as conn:
        conn.execute(
            "INSERT INTO users (id, name, api_key, created_at) VALUES (?, ?, ?, ?)",
            (user.id, user.name, user.api_key, user.created_at),
        )
    return user


def get_by_api_key(api_key: str) -> User | None:
    """Look up a user by API key. Returns None if not found."""
    _init_db()
    with _conn() as conn:
        row = conn.execute(
            "SELECT id, name, api_key, created_at FROM users WHERE api_key = ?", (api_key,)
        ).fetchone()
    return User(*row) if row else None


def get_by_id(user_id: str) -> User | None:
    """Look up a user by id. Returns None if not found."""
    _init_db()
    with _conn() as conn:
        row = conn.execute(
            "SELECT id, name, api_key, created_at FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    return User(*row) if row else None


def list_users() -> list[User]:
    """Return all users ordered by created_at."""
    _init_db()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, name, api_key, created_at FROM users ORDER BY created_at"
        ).fetchall()
    return [User(*row) for row in rows]


def rotate_key(user_id: str) -> User:
    """Generate a new API key for user_id. Raises KeyError if user not found."""
    _init_db()
    new_key = f"ma-{secrets.token_hex(32)}"
    with _conn() as conn:
        updated = conn.execute(
            "UPDATE users SET api_key = ? WHERE id = ? RETURNING id, name, api_key, created_at",
            (new_key, user_id),
        ).fetchone()
    if updated is None:
        raise KeyError(f"User not found: {user_id}")
    return User(*updated)


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)


def _init_db() -> None:
    with _conn() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS users (
                id         TEXT PRIMARY KEY,
                name       TEXT NOT NULL,
                api_key    TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_user_store.py -v
```

Expected: 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/mini_agent/user_store.py tests/test_user_store.py
git commit -m "feat: add user_store with SQLite CRUD and API key management"
```

---

## Task 4: memory_layer user_id scoping

**Files:**
- Modify: `src/mini_agent/memory_layer.py`

- [ ] **Step 1: Add `_mem_path()` helper and update functions**

In `src/mini_agent/memory_layer.py`, replace the module-level `_MEM_PATH` and update both public functions to accept `user_id`:

```python
# Remove this line:
_MEM_PATH = Path("data/memories.jsonl")

# Add this function after the imports:
def _mem_path(user_id: str = "default") -> Path:
    return Path(f"data/users/{user_id}/memories.jsonl")
```

- [ ] **Step 2: Update `load_memories` signature**

Change:
```python
def load_memories(n: int = 20) -> str:
    if not _MEM_PATH.exists():
        return ""
    lines = _MEM_PATH.read_text(encoding="utf-8").splitlines()
```

To:
```python
def load_memories(user_id: str = "default", n: int = 20) -> str:
    mem_path = _mem_path(user_id)
    if not mem_path.exists():
        return ""
    lines = mem_path.read_text(encoding="utf-8").splitlines()
```

- [ ] **Step 3: Update `extract_and_save` signature**

Change:
```python
def extract_and_save(user_input: str, messages: list[Any]) -> None:
    ...
    _MEM_PATH.parent.mkdir(parents=True, exist_ok=True)
    ...
    with _MEM_PATH.open("a", encoding="utf-8") as f:
```

To:
```python
def extract_and_save(user_input: str, messages: list[Any], user_id: str = "default") -> None:
    ...
    mem_path = _mem_path(user_id)
    mem_path.parent.mkdir(parents=True, exist_ok=True)
    ...
    with mem_path.open("a", encoding="utf-8") as f:
```

- [ ] **Step 4: Verify existing smoke test still passes**

```bash
uv run pytest -v 2>/dev/null || echo "no tests yet - run smoke.sh"
bash scripts/smoke.sh 2>&1 | tail -5
```

Expected: smoke tests still pass (CLI uses default "default" user_id).

- [ ] **Step 5: Commit**

```bash
git add src/mini_agent/memory_layer.py
git commit -m "feat: scope memory_layer per user_id"
```

---

## Task 5: agent_loop wiring

**Files:**
- Modify: `src/mini_agent/agent_loop.py`

Wire `user_id`, `context_mgr`, and `skill_registry` into the existing `run()` function.

- [ ] **Step 1: Update imports in agent_loop.py**

Add to the top of `src/mini_agent/agent_loop.py`:

```python
from mini_agent.context_mgr import DEFAULT_CONFIG, maybe_compress
from mini_agent.skill_registry import load as load_skill
from mini_agent.skill_registry import match as match_skill
from mini_agent.skill_registry import scan as scan_skills
```

- [ ] **Step 2: Add user_id parameter and wire all modules**

Replace the entire `run()` function:

```python
def run(user_input: str, user_id: str = "default", system_prompt: str = _SYSTEM) -> str:
    """Run the agent loop for a single user turn. Return the final text reply."""
    scan_skills()
    client, cfg = get_client_and_config("default")

    memory_ctx = load_memories(user_id=user_id)
    full_system = f"{memory_ctx}\n\n{system_prompt}" if memory_ctx else system_prompt

    # Inject matching skill into system prompt
    matched = match_skill(user_input)
    if matched:
        skill_content = load_skill(matched)
        full_system = f"{full_system}\n\n{skill_content}"

    messages: list[Any] = [
        {"role": "system", "content": full_system},
        {"role": "user", "content": user_input},
    ]

    start = time.monotonic()
    response = None

    while True:
        messages = maybe_compress(messages, config=DEFAULT_CONFIG)
        response = client.chat.completions.create(
            model=cfg.model,
            messages=messages,
            tools=get_schemas(),  # type: ignore[arg-type]
            max_tokens=cfg.max_tokens,
        )
        choice = response.choices[0]
        msg = choice.message
        messages.append(msg)

        if choice.finish_reason != "tool_calls":
            break

        for tc in msg.tool_calls or []:
            if not hasattr(tc, "function"):
                continue
            result = dispatch(tc.function.name, tc.function.arguments)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

    reply = msg.content or ""
    usage = response.usage if response else None
    log_run(user_input, reply, messages, time.monotonic() - start, usage)
    extract_and_save(user_input, messages, user_id=user_id)
    return reply
```

- [ ] **Step 3: Verify smoke tests pass**

```bash
bash scripts/smoke.sh 2>&1 | tail -5
```

Expected: all PASS (CLI still works, user_id defaults to "default").

- [ ] **Step 4: Commit**

```bash
git add src/mini_agent/agent_loop.py
git commit -m "feat: wire user_id, context_mgr, skill_registry into agent_loop"
```

---

## Task 6: async run_stream()

**Files:**
- Modify: `src/mini_agent/model_router.py`
- Modify: `src/mini_agent/agent_loop.py`

- [ ] **Step 1: Add get_async_client_and_config to model_router.py**

Add after the existing `get_client_and_config()` function:

```python
from openai import AsyncOpenAI

def get_async_client_and_config(task_type: str = "default") -> tuple[AsyncOpenAI, RouteConfig]:
    """Return an async OpenAI client and route config for the given task type."""
    cfg = ROUTES.get(task_type, ROUTES["default"])
    api_key = os.environ.get(cfg.api_key_env, "")
    return AsyncOpenAI(base_url=cfg.base_url, api_key=api_key), cfg
```

- [ ] **Step 2: Add run_stream() to agent_loop.py**

Add these imports to `agent_loop.py`:

```python
from collections.abc import AsyncGenerator
from mini_agent.model_router import get_async_client_and_config
```

Add after the existing `run()` function:

```python
async def run_stream(
    user_input: str, user_id: str = "default", system_prompt: str = _SYSTEM
) -> AsyncGenerator[dict[str, Any], None]:
    """Async streaming version of run(). Yields SSE event dicts.

    Event types: tool_call, tool_result, text_delta, done.
    """
    scan_skills()
    client, cfg = get_async_client_and_config("default")

    memory_ctx = load_memories(user_id=user_id)
    full_system = f"{memory_ctx}\n\n{system_prompt}" if memory_ctx else system_prompt

    matched = match_skill(user_input)
    if matched:
        full_system = f"{full_system}\n\n{load_skill(matched)}"

    messages: list[Any] = [
        {"role": "system", "content": full_system},
        {"role": "user", "content": user_input},
    ]

    start = time.monotonic()
    response = None

    while True:
        messages = maybe_compress(messages, config=DEFAULT_CONFIG)
        response = await client.chat.completions.create(
            model=cfg.model,
            messages=messages,
            tools=get_schemas(),  # type: ignore[arg-type]
            max_tokens=cfg.max_tokens,
        )
        choice = response.choices[0]
        msg = choice.message
        messages.append(msg)

        if choice.finish_reason != "tool_calls":
            break

        for tc in msg.tool_calls or []:
            if not hasattr(tc, "function"):
                continue
            yield {"type": "tool_call", "name": tc.function.name, "args": tc.function.arguments}
            result = dispatch(tc.function.name, tc.function.arguments)
            yield {"type": "tool_result", "name": tc.function.name, "content": result}
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

    reply = msg.content or ""
    yield {"type": "text_delta", "content": reply}
    yield {"type": "done", "content": reply}

    usage = response.usage if response else None
    log_run(user_input, reply, messages, time.monotonic() - start, usage)
    extract_and_save(user_input, messages, user_id=user_id)
```

- [ ] **Step 3: Lint check**

```bash
uv run ruff check src/mini_agent/agent_loop.py src/mini_agent/model_router.py
```

Expected: no errors. Fix any line-length issues if reported.

- [ ] **Step 4: Commit**

```bash
git add src/mini_agent/agent_loop.py src/mini_agent/model_router.py
git commit -m "feat: add async run_stream() for SSE and get_async_client_and_config"
```

---

## Task 7: server.py

**Files:**
- Create: `src/mini_agent/server.py`
- Create: `tests/test_server.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_server.py`:

```python
import pytest
from fastapi.testclient import TestClient

import mini_agent.user_store as us
from mini_agent.server import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(us, "DB_PATH", tmp_path / "users.db")
    return TestClient(app)


@pytest.fixture()
def auth_headers(tmp_path, monkeypatch):
    monkeypatch.setattr(us, "DB_PATH", tmp_path / "users.db")
    user = us.create_user("Tester")
    return {"Authorization": f"Bearer {user.api_key}"}


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_chat_no_auth(client):
    resp = client.post("/chat", json={"message": "hello"})
    assert resp.status_code == 422  # missing header


def test_chat_invalid_token(client):
    resp = client.post(
        "/chat",
        json={"message": "hello"},
        headers={"Authorization": "Bearer ma-invalid"},
    )
    assert resp.status_code == 401


def test_chat_valid_token_streams(tmp_path, monkeypatch):
    import mini_agent.server as srv
    import mini_agent.user_store as us2

    monkeypatch.setattr(us2, "DB_PATH", tmp_path / "users.db")

    async def fake_stream(msg: str, user_id: str):  # type: ignore[misc]
        yield {"type": "text_delta", "content": "hi"}
        yield {"type": "done", "content": "hi"}

    monkeypatch.setattr(srv, "run_stream", fake_stream)

    user = us2.create_user("StreamTester")
    with TestClient(app) as c:
        resp = c.post(
            "/chat",
            json={"message": "hello"},
            headers={"Authorization": f"Bearer {user.api_key}"},
        )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    assert "done" in resp.text
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_server.py -v
```

Expected: `ImportError: No module named 'mini_agent.server'`

- [ ] **Step 3: Implement server.py**

Create `src/mini_agent/server.py`:

```python
"""FastAPI HTTP server: POST /chat (SSE), GET /health."""

import json
from collections.abc import AsyncGenerator

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from mini_agent.agent_loop import run_stream
from mini_agent.user_store import get_by_api_key

app = FastAPI(title="mini-agent")


class ChatRequest(BaseModel):
    message: str


async def _require_auth(authorization: str = Header()) -> str:
    """Extract user_id from Bearer token. Raises 401 if invalid."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    api_key = authorization.removeprefix("Bearer ").strip()
    user = get_by_api_key(api_key)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return user.id


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat")
async def chat(
    req: ChatRequest, user_id: str = Depends(_require_auth)
) -> StreamingResponse:
    async def _stream() -> AsyncGenerator[str, None]:
        async for event in run_stream(req.message, user_id=user_id):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream")
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_server.py -v
```

Expected: 4 tests PASS.

- [ ] **Step 5: Lint check**

```bash
uv run ruff check src/mini_agent/server.py
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add src/mini_agent/server.py tests/test_server.py
git commit -m "feat: add FastAPI server with SSE /chat and /health endpoints"
```

---

## Task 8: admin.py

**Files:**
- Create: `src/mini_agent/admin.py`

- [ ] **Step 1: Implement admin.py**

Create `src/mini_agent/admin.py`:

```python
"""Admin CLI for user management. Usage: uv run mini-agent-admin <command>"""

import argparse
import sys

from mini_agent.user_store import create_user, list_users, rotate_key


def main() -> None:
    parser = argparse.ArgumentParser(prog="mini-agent-admin", description="User management CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_create = sub.add_parser("create-user", help="Create a new user")
    p_create.add_argument("--name", required=True, help="Display name")

    sub.add_parser("list-users", help="List all users")

    p_rotate = sub.add_parser("rotate-key", help="Rotate a user's API key")
    p_rotate.add_argument("--user-id", required=True, help="User UUID")

    args = parser.parse_args()

    if args.cmd == "create-user":
        user = create_user(args.name)
        print(f"User created.")
        print(f"  id:      {user.id}")
        print(f"  name:    {user.name}")
        print(f"  api_key: {user.api_key}  ← save this, shown once")

    elif args.cmd == "list-users":
        users = list_users()
        if not users:
            print("No users.")
            return
        print(f"{'ID':<38}  {'NAME':<20}  CREATED")
        for u in users:
            print(f"{u.id}  {u.name:<20}  {u.created_at}")

    elif args.cmd == "rotate-key":
        try:
            user = rotate_key(args.user_id)
        except KeyError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        print(f"Key rotated for {user.name}.")
        print(f"  new api_key: {user.api_key}  ← save this, shown once")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify CLI works**

```bash
uv run mini-agent-admin create-user --name "TestUser"
```

Expected output:
```
User created.
  id:      <uuid>
  name:    TestUser
  api_key: ma-<64 hex chars>  ← save this, shown once
```

```bash
uv run mini-agent-admin list-users
```

Expected: table with TestUser row.

- [ ] **Step 3: Run full test suite**

```bash
uv run pytest -v
```

Expected: all tests PASS.

- [ ] **Step 4: Lint + type check**

```bash
uv run ruff check src/
uv run mypy src/
```

Fix any errors before committing.

- [ ] **Step 5: Final commit**

```bash
git add src/mini_agent/admin.py
git commit -m "feat: add admin CLI for user management (create-user, list-users, rotate-key)"
```

---

## Phase 2 (not in this plan)

- `agent_policy.py` — per-agent tool allowlist
- `user_grant.py` — OAuth 2.1 user token delegation
- `mcp_client.py` — MCP HTTP client, tool_registry integration
