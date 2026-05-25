"""Cross-session memory: extract facts after each run, inject before the next."""

import json
import time
from pathlib import Path
from typing import Any

from fleetent.model_router import get_client_and_config


def _mem_path(user_id: str = "default") -> Path:
    return Path(f"data/users/{user_id}/memories.jsonl")


_EXTRACT_SYSTEM = (
    "You are a memory extractor. From the conversation below, extract facts about the user "
    "worth remembering long-term (name, preferences, goals, ongoing context). "
    "Return a JSON array of short fact strings. "
    'If nothing is worth remembering, return []. '
    'Example: ["User prefers Chinese replies", "User is learning agent development"]'
)


def load_memories(user_id: str = "default", n: int = 20) -> str:
    """Return the last n memories as a formatted string for the system prompt.

    Returns empty string if no memories exist yet.
    """
    mem_path = _mem_path(user_id)
    if not mem_path.exists():
        return ""
    lines = mem_path.read_text(encoding="utf-8").splitlines()
    recent = lines[-n:] if len(lines) > n else lines
    facts: list[str] = []
    for line in recent:
        try:
            entry = json.loads(line)
            if isinstance(entry, dict) and isinstance(entry.get("text"), str):
                facts.append(f"- {entry['text']}")
        except json.JSONDecodeError:
            continue
    if not facts:
        return ""
    return "[Memory]\n" + "\n".join(facts)


def extract_and_save(user_input: str, messages: list[Any], user_id: str = "default") -> None:
    """Call a cheap LLM to extract memorable facts and append them to JSONL."""
    client, cfg = get_client_and_config("memory_extraction")
    convo = _messages_to_text(messages)

    response = client.chat.completions.create(
        model=cfg.model,
        messages=[
            {"role": "system", "content": _EXTRACT_SYSTEM},
            {"role": "user", "content": convo},
        ],
        max_tokens=cfg.max_tokens,
    )

    raw = _strip_markdown_fence(response.choices[0].message.content or "[]")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return

    if not isinstance(parsed, list):
        return
    facts = [f for f in parsed if isinstance(f, str) and f.strip()]
    if not facts:
        return

    mem_path = _mem_path(user_id)
    mem_path.parent.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with mem_path.open("a", encoding="utf-8") as f:
        for fact in facts:
            entry: dict[str, str] = {"ts": ts, "text": fact.strip(), "source_input": user_input}
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _strip_markdown_fence(text: str) -> str:
    """Remove ```json ... ``` or ``` ... ``` wrappers that LLMs sometimes add."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        text = text.rsplit("```", 1)[0]
    return text.strip()


def _messages_to_text(messages: list[Any]) -> str:
    """Flatten messages to plain text, skipping system and tool messages."""
    lines: list[str] = []
    for msg in messages:
        if isinstance(msg, dict):
            role, content = msg.get("role", ""), str(msg.get("content", ""))
        elif hasattr(msg, "role"):
            role, content = msg.role, str(msg.content or "")
        else:
            continue
        if role in ("system", "tool"):
            continue
        lines.append(f"{role}: {content}")
    return "\n".join(lines)
