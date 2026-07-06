"""Field mapping: ``${...}`` placeholder parsing and runtime rendering.

The Python-simplified analogue of Eino's field mapping. Two named roots only:
``${inputs.<path>}`` (run start params) and ``${steps.<id>.output.<path>}``
(upstream step output). ``<path>`` is a dotted path over dict keys and
non-negative list indices. A value that is exactly one placeholder preserves the
resolved value's type; a placeholder embedded in surrounding text is
stringified. Anything unresolvable fails closed (raises), never silently None.

No third-party JSONPath dependency — the grammar is deliberately tiny.
"""

from __future__ import annotations

import re
from typing import Any

from fleetent.workflow.errors import WorkflowMappingError

# One ``${ ... }`` occurrence; inner text captured. Non-greedy so multiple
# placeholders in one string are matched independently.
_PLACEHOLDER_RE = re.compile(r"\$\{([^}]*)\}")

_INPUTS_ROOT = "inputs"
_STEPS_ROOT = "steps"


def extract_refs(value: Any) -> list[str]:
    """Return every placeholder inner-ref found anywhere in ``value`` (recursively).

    Walks strings, dict values, and list items. Returns raw inner refs such as
    ``"inputs.channel"`` or ``"steps.fetch.output.text"`` (order-preserving,
    with duplicates) for the caller to parse/validate.
    """
    out: list[str] = []
    _collect(value, out)
    return out


def _collect(value: Any, out: list[str]) -> None:
    if isinstance(value, str):
        out.extend(m.group(1).strip() for m in _PLACEHOLDER_RE.finditer(value))
    elif isinstance(value, dict):
        for v in value.values():
            _collect(v, out)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _collect(v, out)


class Ref:
    """A parsed placeholder reference (validated syntax)."""

    __slots__ = ("root", "step_id", "path")

    def __init__(self, root: str, step_id: str | None, path: tuple[str, ...]) -> None:
        self.root = root
        self.step_id = step_id
        self.path = path


def parse_ref(ref: str) -> Ref:
    """Parse and syntactically validate a placeholder inner-ref.

    Raises ``WorkflowMappingError`` on an unknown root or malformed ``steps`` ref.
    Accepts ``inputs.<path...>`` and ``steps.<id>.output.<path...>``.
    """
    parts = [p for p in ref.split(".") if p != ""]
    if not parts:
        raise WorkflowMappingError(f"empty placeholder reference: ${{{ref}}}")
    root = parts[0]
    if root == _INPUTS_ROOT:
        return Ref(_INPUTS_ROOT, None, tuple(parts[1:]))
    if root == _STEPS_ROOT:
        # steps.<id>.output[.<path...>]
        if len(parts) < 3 or parts[2] != "output":
            raise WorkflowMappingError(
                f"invalid steps reference ${{{ref}}}: expected steps.<id>.output.<path>"
            )
        return Ref(_STEPS_ROOT, parts[1], tuple(parts[3:]))
    raise WorkflowMappingError(
        f"unknown placeholder root {root!r} in ${{{ref}}}: only 'inputs' and 'steps' are allowed"
    )


def referenced_step_ids(value: Any) -> set[str]:
    """The set of step ids referenced by ``${steps.<id>...}`` anywhere in ``value``."""
    ids: set[str] = set()
    for ref in extract_refs(value):
        parsed = parse_ref(ref)  # also validates syntax
        if parsed.root == _STEPS_ROOT and parsed.step_id is not None:
            ids.add(parsed.step_id)
    return ids


def validate_syntax(value: Any) -> None:
    """Raise ``WorkflowMappingError`` if any placeholder in ``value`` is malformed."""
    for ref in extract_refs(value):
        parse_ref(ref)


def render(value: Any, context: dict[str, Any]) -> Any:
    """Resolve every placeholder in ``value`` against ``context`` (fail-closed).

    ``context`` shape: ``{"inputs": {...}, "steps": {"<id>": {"output": {...}}}}``.
    A string that is exactly one placeholder returns the resolved value with its
    original type preserved; otherwise placeholders are stringified into the text.
    Dicts and lists are rendered recursively. An unresolvable path raises
    ``WorkflowMappingError`` — it is never silently dropped to None/empty.
    """
    if isinstance(value, str):
        return _render_str(value, context)
    if isinstance(value, dict):
        return {k: render(v, context) for k, v in value.items()}
    if isinstance(value, list):
        return [render(v, context) for v in value]
    return value


def _render_str(text: str, context: dict[str, Any]) -> Any:
    matches = list(_PLACEHOLDER_RE.finditer(text))
    if not matches:
        return text
    # Exact single-placeholder value → preserve resolved type.
    if len(matches) == 1 and matches[0].span() == (0, len(text)):
        return _resolve(matches[0].group(1).strip(), context)

    def _sub(m: re.Match[str]) -> str:
        resolved = _resolve(m.group(1).strip(), context)
        return resolved if isinstance(resolved, str) else _stringify(resolved)

    return _PLACEHOLDER_RE.sub(_sub, text)


def _stringify(value: Any) -> str:
    import json

    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _resolve(ref: str, context: dict[str, Any]) -> Any:
    parsed = parse_ref(ref)
    if parsed.root == _INPUTS_ROOT:
        base = context.get(_INPUTS_ROOT, {})
        return _walk(base, parsed.path, ref)
    # steps.<id>.output.<path>
    steps = context.get(_STEPS_ROOT, {})
    if parsed.step_id not in steps:
        raise WorkflowMappingError(f"unknown step in reference ${{{ref}}}: {parsed.step_id!r}")
    output = steps[parsed.step_id].get("output")
    return _walk(output, parsed.path, ref)


def _walk(base: Any, path: tuple[str, ...], ref: str) -> Any:
    cur = base
    for seg in path:
        if isinstance(cur, dict):
            if seg not in cur:
                raise WorkflowMappingError(f"key {seg!r} not found resolving ${{{ref}}}")
            cur = cur[seg]
        elif isinstance(cur, list):
            try:
                idx = int(seg)
            except ValueError as exc:
                raise WorkflowMappingError(
                    f"list index {seg!r} is not an integer resolving ${{{ref}}}"
                ) from exc
            if idx < 0 or idx >= len(cur):
                raise WorkflowMappingError(f"index {idx} out of range resolving ${{{ref}}}")
            cur = cur[idx]
        else:
            raise WorkflowMappingError(
                f"cannot descend into {type(cur).__name__} at {seg!r} resolving ${{{ref}}}"
            )
    return cur
