# mini-agent

Minimal agent loop in ~360 lines of Python. No framework. Read it in 30 minutes.

Built as a learning project to understand agent internals from first principles —
tool calling protocol, cross-session memory, multi-provider routing — without any
abstraction layer getting in the way.

## Quick Start

```bash
# Prerequisites: Python 3.12+, uv
git clone https://github.com/raw34/mini-agent.git
cd mini-agent
uv sync
export ANTHROPIC_API_KEY=sk-ant-...

uv run mini-agent "What time is it, and what is 123 * 456?"
```

## Architecture

```
user input
    │
    ▼
agent_loop.run()          ← the while loop (agent_loop.py)
    │   ┌─────────────────────────────────┐
    │   │  load_memories()                │  inject cross-session facts
    │   │  [Memory] User's name is Randy  │
    │   └─────────────────────────────────┘
    │
    ▼
LLM (model_router.py)     ← OpenAI-compatible, swap provider by changing ROUTES
    │
    ├── finish_reason == "tool_calls"?
    │       │
    │       ▼
    │   tool_registry.dispatch()   ← execute tools, append role:"tool" results
    │       │
    │       └── loop back to LLM
    │
    └── finish_reason == "stop"
            │
            ▼
        log_run()             ← append to data/traces.jsonl (eval_logger.py)
        extract_and_save()    ← haiku extracts facts → data/memories.jsonl
            │
            ▼
        return reply
```

## Modules

| File | Lines | Role |
|------|-------|------|
| `agent_loop.py` | 53 | The while loop. Wires everything together. |
| `model_router.py` | 47 | Maps task types to provider configs. |
| `tool_registry.py` | 63 | `@tool` decorator, schema building, dispatch. |
| `tools.py` | 34 | Built-in tools: `calculate`, `get_current_time`, `read_file`. |
| `eval_logger.py` | 47 | Appends JSONL traces after each run. |
| `memory_layer.py` | 99 | Extract facts (haiku) → store → inject into system prompt. |

## Adding a Tool

```python
# src/mini_agent/tools.py
from mini_agent.tool_registry import tool

@tool
def my_tool(param: str) -> str:
    """One-line description shown to the LLM."""
    return "result"
```

The `@tool` decorator registers the function and auto-generates its JSON Schema from type annotations and the docstring.

## Switching Providers

Change two fields in `src/mini_agent/model_router.py`:

```python
ROUTES = {
    "default": RouteConfig(
        base_url="https://api.openai.com/v1/",  # any OpenAI-compatible endpoint
        model="gpt-4o-mini",
        api_key_env="OPENAI_API_KEY",
        max_tokens=4096,
    ),
    ...
}
```

No other code changes needed. The agent loop, tool registry, and memory layer are all provider-agnostic.

## Internals

Per-module deep dives in [`docs/internals/`](docs/internals/):
- [model_router.md](docs/internals/model_router.md)
- [tool_registry.md](docs/internals/tool_registry.md)
- [agent_loop.md](docs/internals/agent_loop.md)
- [eval_logger.md](docs/internals/eval_logger.md)
- [memory_layer.md](docs/internals/memory_layer.md)

## License

Apache 2.0. Copyright 2026 Randy Chang.
