"""Built-in, read-only Agent templates for the console's "create from template" flow.

Module-level constants only — no IO, not stored in the DB, not editable via the API.
Starting an agent from a template pre-fills recommended allowed_tools and prompt.
"""

import copy
from typing import Any

_TEMPLATES: dict[str, dict[str, Any]] = {
    "readonly-qa": {
        "display_name": "只读问答 Agent",
        "allowed_tools": ["read_*", "search_*"],
        "system_prompt": "You are a read-only question-answering assistant. "
        "Answer from available knowledge and never perform write or destructive actions.",
    },
    "ops": {
        "display_name": "运维 Agent",
        "allowed_tools": ["read_*", "exec_*", "github__*"],
        "system_prompt": "You are an operations assistant. Help diagnose and operate systems; "
        "request approval before any high-risk action.",
    },
    "support": {
        "display_name": "客服 Agent",
        "allowed_tools": ["read_*", "search_*", "ticket__*"],
        "system_prompt": "You are a customer-support assistant. Be empathetic, accurate, "
        "and escalate to a human when unsure.",
    },
}


def list_templates() -> list[dict[str, Any]]:
    """Return all built-in templates (deep copies, so callers cannot mutate the constants)."""
    return [{"id": tid, **copy.deepcopy(spec)} for tid, spec in _TEMPLATES.items()]


def get_template(template_id: str) -> dict[str, Any] | None:
    spec = _TEMPLATES.get(template_id)
    return {"id": template_id, **copy.deepcopy(spec)} if spec else None
