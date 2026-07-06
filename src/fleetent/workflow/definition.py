"""Workflow definition parsing and load-time validation.

The Compile()-equivalent for fleetent workflows: turn a parsed YAML mapping into
a validated, frozen ``WorkflowDef`` — or fail closed with a
``WorkflowDefinitionError`` that names the offending step/field. Validation
covers structure, per-type required fields, unknown-field rejection, reference
existence, placeholder syntax, DAG acyclicity (Kahn), and tool-arg conformance
against the registered tool schema.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fleetent.workflow.errors import WorkflowDefinitionError, WorkflowMappingError
from fleetent.workflow.mapping import referenced_step_ids, validate_syntax

STEP_TYPES = frozenset({"tool", "agent", "notify"})

DEFAULT_TIMEOUT_SECONDS = 300
DEFAULT_MAX_ATTEMPTS = 0

# Allowed keys per step type (in addition to the common ones) — anything else is a typo.
_COMMON_STEP_KEYS = frozenset({"id", "type", "depends_on", "timeout_seconds", "retry"})
_TYPE_STEP_KEYS: dict[str, frozenset[str]] = {
    "tool": frozenset({"tool", "args"}),
    "agent": frozenset({"agent", "prompt", "output_schema"}),
    "notify": frozenset({"text", "to"}),
}
_TOP_LEVEL_KEYS = frozenset({"name", "description", "inputs", "steps"})


@dataclass(frozen=True)
class InputDef:
    name: str
    type: str
    default: Any
    required: bool


@dataclass(frozen=True)
class StepDef:
    id: str
    type: str
    depends_on: tuple[str, ...]
    timeout_seconds: int
    max_attempts: int
    # tool
    tool: str | None = None
    args: dict[str, Any] = field(default_factory=dict)
    # agent
    agent: str | None = None
    prompt: str | None = None
    output_schema: dict[str, Any] | None = None
    # notify
    text: str | None = None
    to: Any = None


@dataclass(frozen=True)
class WorkflowDef:
    name: str
    description: str
    inputs: dict[str, InputDef]
    steps: tuple[StepDef, ...]
    # step_id -> set of control-predecessor step ids (depends_on ∪ data-ref-implied)
    control_deps: dict[str, frozenset[str]]

    def step(self, step_id: str) -> StepDef:
        for s in self.steps:
            if s.id == step_id:
                return s
        raise KeyError(step_id)


def parse_definition(raw: dict[str, Any]) -> WorkflowDef:
    """Validate a parsed workflow mapping and return a frozen ``WorkflowDef``.

    Raises ``WorkflowDefinitionError`` (naming the offending step/field) on any
    structural, reference, cycle, placeholder-syntax, or tool-schema violation.
    """
    if not isinstance(raw, dict):
        raise WorkflowDefinitionError("workflow definition must be a mapping")
    unknown_top = set(raw) - _TOP_LEVEL_KEYS
    if unknown_top:
        raise WorkflowDefinitionError(f"unknown top-level field(s): {sorted(unknown_top)}")

    name = raw.get("name")
    if not isinstance(name, str) or not name:
        raise WorkflowDefinitionError("workflow 'name' is required and must be a non-empty string")
    description = raw.get("description", "")
    if not isinstance(description, str):
        raise WorkflowDefinitionError("workflow 'description' must be a string")

    inputs = _parse_inputs(raw.get("inputs", {}))

    raw_steps = raw.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise WorkflowDefinitionError("workflow 'steps' is required and must be a non-empty list")

    steps = tuple(_parse_step(s, i) for i, s in enumerate(raw_steps))

    ids = [s.id for s in steps]
    dupes = {x for x in ids if ids.count(x) > 1}
    if dupes:
        raise WorkflowDefinitionError(f"duplicate step id(s): {sorted(dupes)}")
    id_set = set(ids)

    control_deps = _build_control_deps(steps, id_set)
    _detect_cycle(steps, control_deps)
    _validate_tool_steps(steps)

    return WorkflowDef(
        name=name,
        description=description,
        inputs=inputs,
        steps=steps,
        control_deps=control_deps,
    )


def _parse_inputs(raw_inputs: Any) -> dict[str, InputDef]:
    if not isinstance(raw_inputs, dict):
        raise WorkflowDefinitionError("'inputs' must be a mapping of name -> {type, default}")
    out: dict[str, InputDef] = {}
    for iname, spec in raw_inputs.items():
        spec = spec or {}
        if not isinstance(spec, dict):
            raise WorkflowDefinitionError(f"input {iname!r} spec must be a mapping")
        has_default = "default" in spec
        out[iname] = InputDef(
            name=iname,
            type=spec.get("type", "string"),
            default=spec.get("default"),
            required=not has_default,
        )
    return out


def _parse_step(raw: Any, index: int) -> StepDef:
    if not isinstance(raw, dict):
        raise WorkflowDefinitionError(f"step #{index} must be a mapping")
    sid = raw.get("id")
    if not isinstance(sid, str) or not sid:
        raise WorkflowDefinitionError(f"step #{index} is missing a non-empty 'id'")
    stype = raw.get("type")
    if stype not in STEP_TYPES:
        raise WorkflowDefinitionError(
            f"step {sid!r} has invalid type {stype!r}; must be one of {sorted(STEP_TYPES)}"
        )

    allowed = _COMMON_STEP_KEYS | _TYPE_STEP_KEYS[stype]
    unknown = set(raw) - allowed
    if unknown:
        raise WorkflowDefinitionError(f"step {sid!r} has unknown field(s): {sorted(unknown)}")

    depends_on = raw.get("depends_on", [])
    if not isinstance(depends_on, list) or not all(isinstance(d, str) for d in depends_on):
        raise WorkflowDefinitionError(f"step {sid!r} 'depends_on' must be a list of step ids")

    timeout_seconds = raw.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
    if (
        not isinstance(timeout_seconds, int)
        or isinstance(timeout_seconds, bool)
        or timeout_seconds <= 0
    ):
        raise WorkflowDefinitionError(f"step {sid!r} 'timeout_seconds' must be a positive integer")

    retry = raw.get("retry", {}) or {}
    if not isinstance(retry, dict):
        raise WorkflowDefinitionError(f"step {sid!r} 'retry' must be a mapping")
    max_attempts = retry.get("max_attempts", DEFAULT_MAX_ATTEMPTS)
    if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or max_attempts < 0:
        raise WorkflowDefinitionError(
            f"step {sid!r} 'retry.max_attempts' must be a non-negative integer"
        )

    common = dict(
        id=sid,
        type=stype,
        depends_on=tuple(depends_on),
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
    )

    if stype == "tool":
        tool = raw.get("tool")
        if not isinstance(tool, str) or not tool:
            raise WorkflowDefinitionError(f"tool step {sid!r} requires a 'tool' name")
        args = raw.get("args", {})
        if not isinstance(args, dict):
            raise WorkflowDefinitionError(f"tool step {sid!r} 'args' must be a mapping")
        step = StepDef(**common, tool=tool, args=args)
    elif stype == "agent":
        prompt = raw.get("prompt")
        if not isinstance(prompt, str) or not prompt:
            raise WorkflowDefinitionError(f"agent step {sid!r} requires a 'prompt'")
        agent = raw.get("agent")
        if agent is not None and not isinstance(agent, str):
            raise WorkflowDefinitionError(f"agent step {sid!r} 'agent' must be a string")
        output_schema = raw.get("output_schema")
        if output_schema is not None and not isinstance(output_schema, dict):
            raise WorkflowDefinitionError(f"agent step {sid!r} 'output_schema' must be a mapping")
        step = StepDef(**common, agent=agent, prompt=prompt, output_schema=output_schema)
    else:  # notify
        text = raw.get("text")
        if not isinstance(text, str) or not text:
            raise WorkflowDefinitionError(f"notify step {sid!r} requires 'text'")
        step = StepDef(**common, text=text, to=raw.get("to"))

    # Placeholder syntax is validated across every field of the step (fail closed here so
    # a bad ``${...}`` is caught at load, not at run).
    try:
        validate_syntax(_step_mapped_fields(step))
    except WorkflowMappingError as exc:
        raise WorkflowDefinitionError(f"step {sid!r}: {exc}") from exc
    return step


def _step_mapped_fields(step: StepDef) -> dict[str, Any]:
    """The subset of a step's fields that may contain ``${...}`` placeholders."""
    if step.type == "tool":
        return {"args": step.args}
    if step.type == "agent":
        return {"prompt": step.prompt}
    return {"text": step.text, "to": step.to}


def _build_control_deps(steps: tuple[StepDef, ...], id_set: set[str]) -> dict[str, frozenset[str]]:
    deps: dict[str, frozenset[str]] = {}
    for s in steps:
        control: set[str] = set()
        for d in s.depends_on:
            if d not in id_set:
                raise WorkflowDefinitionError(f"step {s.id!r} depends_on unknown step {d!r}")
            control.add(d)
        for ref_id in referenced_step_ids(_step_mapped_fields(s)):
            if ref_id not in id_set:
                raise WorkflowDefinitionError(f"step {s.id!r} references unknown step {ref_id!r}")
            control.add(ref_id)
        deps[s.id] = frozenset(control)
    return deps


def _detect_cycle(steps: tuple[StepDef, ...], control_deps: dict[str, frozenset[str]]) -> None:
    """Kahn topological sort; any remaining node with unresolved indegree is on a cycle."""
    indegree = {s.id: len(control_deps[s.id]) for s in steps}
    # successors: for each predecessor, who depends on it
    successors: dict[str, list[str]] = {s.id: [] for s in steps}
    for sid, preds in control_deps.items():
        for p in preds:
            successors[p].append(sid)

    ready = [sid for sid, deg in indegree.items() if deg == 0]
    seen = 0
    while ready:
        node = ready.pop()
        seen += 1
        for succ in successors[node]:
            indegree[succ] -= 1
            if indegree[succ] == 0:
                ready.append(succ)

    if seen != len(steps):
        on_cycle = sorted(sid for sid, deg in indegree.items() if deg > 0)
        raise WorkflowDefinitionError(f"workflow has a dependency cycle involving: {on_cycle}")


def _validate_tool_steps(steps: tuple[StepDef, ...]) -> None:
    from fleetent.tools import registry

    for s in steps:
        if s.type != "tool":
            continue
        assert s.tool is not None
        if not registry.is_registered(s.tool):
            raise WorkflowDefinitionError(
                f"tool step {s.id!r} references unregistered tool {s.tool!r}"
            )
        schema = registry.get_schema(s.tool)
        if schema is None:
            raise WorkflowDefinitionError(
                f"tool step {s.id!r} references unregistered tool {s.tool!r}"
            )
        params = schema.get("function", {}).get("parameters", {})
        required = params.get("required", [])
        properties = params.get("properties", {})
        for req in required:
            if req not in s.args:
                raise WorkflowDefinitionError(
                    f"tool step {s.id!r} missing required arg {req!r} for tool {s.tool!r}"
                )
        for arg_name, arg_value in s.args.items():
            if _contains_placeholder(arg_value):
                continue  # mapped value: type check deferred to runtime
            expected = properties.get(arg_name, {}).get("type")
            if expected and not _json_type_matches(arg_value, expected):
                raise WorkflowDefinitionError(
                    f"tool step {s.id!r} arg {arg_name!r} literal type mismatch: "
                    f"expected {expected}, got {type(arg_value).__name__}"
                )


def _contains_placeholder(value: Any) -> bool:
    from fleetent.workflow.mapping import extract_refs

    return bool(extract_refs(value))


def _json_type_matches(value: Any, json_type: str) -> bool:
    if json_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if json_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if json_type == "boolean":
        return isinstance(value, bool)
    if json_type == "string":
        return isinstance(value, str)
    if json_type == "array":
        return isinstance(value, list)
    if json_type == "object":
        return isinstance(value, dict)
    return True
