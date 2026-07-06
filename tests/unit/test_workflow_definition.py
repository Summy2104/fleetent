"""Unit tests for workflow definition parsing and load-time validation.

Pure parsing/validation logic (no DB, no LLM): structural checks, DAG cycle
detection, reference existence, placeholder syntax, and tool-schema conformance.
Tool registry lookups are monkeypatched so these stay hermetic.
"""

import pytest

from fleetent.workflow.definition import WorkflowDefinitionError, parse_definition


def _tool_step(id_="fetch", **over):
    step = {"id": id_, "type": "tool", "tool": "web_fetch", "args": {}}
    step.update(over)
    return step


def _base(**over):
    d = {
        "name": "demo",
        "description": "demo flow",
        "steps": [_tool_step()],
    }
    d.update(over)
    return d


@pytest.fixture(autouse=True)
def _stub_registry(monkeypatch):
    """Default: every referenced tool exists with a permissive schema (no required args)."""
    from fleetent.tools import registry

    schemas = {
        "web_fetch": {
            "type": "function",
            "function": {
                "name": "web_fetch",
                "parameters": {
                    "type": "object",
                    "properties": {"url": {"type": "string"}},
                    "required": [],
                },
            },
        }
    }
    monkeypatch.setattr(registry, "get_schema", lambda name: schemas.get(name))
    monkeypatch.setattr(registry, "is_registered", lambda name: name in schemas)
    return schemas


# ── 1.1 structural parsing ────────────────────────────────────────────────────


def test_valid_three_step_definition_parses():
    raw = _base(
        inputs={"channel": {"type": "string", "default": "#x"}},
        steps=[
            _tool_step(),
            {
                "id": "analyze",
                "type": "agent",
                "agent": "analyst",
                "prompt": "sum ${steps.fetch.output.text}",
            },
            {
                "id": "send",
                "type": "notify",
                "text": "${steps.analyze.output.text}",
                "depends_on": ["analyze"],
            },
        ],
    )
    wf = parse_definition(raw)
    assert wf.name == "demo"
    assert [s.id for s in wf.steps] == ["fetch", "analyze", "send"]
    assert wf.steps[0].timeout_seconds == 300  # default
    assert wf.steps[0].max_attempts == 0  # default


def test_missing_type_specific_field_rejected():
    raw = _base(steps=[{"id": "fetch", "type": "tool"}])  # no `tool`
    with pytest.raises(WorkflowDefinitionError, match="fetch"):
        parse_definition(raw)


def test_unknown_step_field_rejected():
    raw = _base(steps=[_tool_step(depend_on=["x"])])  # typo of depends_on
    with pytest.raises(WorkflowDefinitionError, match="depend_on"):
        parse_definition(raw)


def test_unknown_step_type_rejected():
    raw = _base(steps=[{"id": "s", "type": "franken", "tool": "web_fetch"}])
    with pytest.raises(WorkflowDefinitionError):
        parse_definition(raw)


def test_empty_steps_rejected():
    with pytest.raises(WorkflowDefinitionError):
        parse_definition(_base(steps=[]))


def test_duplicate_step_id_rejected():
    raw = _base(steps=[_tool_step("a"), _tool_step("a")])
    with pytest.raises(WorkflowDefinitionError, match="a"):
        parse_definition(raw)


# ── 1.3 DAG validation ────────────────────────────────────────────────────────


def test_cycle_via_depends_on_and_data_ref_rejected():
    raw = _base(
        steps=[
            {"id": "a", "type": "agent", "prompt": "x", "depends_on": ["b"]},
            {"id": "b", "type": "agent", "prompt": "${steps.a.output.text}"},
        ]
    )
    with pytest.raises(WorkflowDefinitionError, match="cycle|环|a|b"):
        parse_definition(raw)


def test_self_reference_rejected():
    raw = _base(steps=[{"id": "a", "type": "agent", "prompt": "${steps.a.output.text}"}])
    with pytest.raises(WorkflowDefinitionError):
        parse_definition(raw)


def test_depends_on_unknown_step_rejected():
    raw = _base(steps=[_tool_step("a", depends_on=["ghost"])])
    with pytest.raises(WorkflowDefinitionError, match="ghost"):
        parse_definition(raw)


def test_data_ref_unknown_step_rejected():
    raw = _base(steps=[{"id": "a", "type": "notify", "text": "${steps.ghost.output.x}"}])
    with pytest.raises(WorkflowDefinitionError, match="ghost"):
        parse_definition(raw)


def test_data_ref_implies_control_dependency():
    raw = _base(
        steps=[
            {"id": "analyze", "type": "agent", "prompt": "hi"},
            {"id": "send", "type": "notify", "text": "${steps.analyze.output.summary}"},
        ]
    )
    wf = parse_definition(raw)
    assert "analyze" in wf.control_deps["send"]


# ── 1.5 tool schema conformance ───────────────────────────────────────────────


def test_unregistered_tool_rejected(monkeypatch):
    from fleetent.tools import registry

    monkeypatch.setattr(registry, "get_schema", lambda name: None)
    monkeypatch.setattr(registry, "is_registered", lambda name: False)
    with pytest.raises(WorkflowDefinitionError, match="web_fetch"):
        parse_definition(_base())


def test_missing_required_arg_rejected(monkeypatch):
    from fleetent.tools import registry

    schema = {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
    }
    monkeypatch.setattr(registry, "get_schema", lambda name: schema)
    monkeypatch.setattr(registry, "is_registered", lambda name: True)
    with pytest.raises(WorkflowDefinitionError, match="url"):
        parse_definition(_base(steps=[_tool_step(args={})]))


def test_literal_type_mismatch_rejected(monkeypatch):
    from fleetent.tools import registry

    schema = {
        "type": "function",
        "function": {
            "name": "counter",
            "parameters": {
                "type": "object",
                "properties": {"count": {"type": "integer"}},
                "required": ["count"],
            },
        },
    }
    monkeypatch.setattr(registry, "get_schema", lambda name: schema)
    monkeypatch.setattr(registry, "is_registered", lambda name: True)
    raw = _base(steps=[{"id": "s", "type": "tool", "tool": "counter", "args": {"count": "abc"}}])
    with pytest.raises(WorkflowDefinitionError, match="count"):
        parse_definition(raw)


def test_mapped_arg_type_deferred(monkeypatch):
    from fleetent.tools import registry

    schema = {
        "type": "function",
        "function": {
            "name": "counter",
            "parameters": {
                "type": "object",
                "properties": {"count": {"type": "integer"}},
                "required": ["count"],
            },
        },
    }
    monkeypatch.setattr(registry, "get_schema", lambda name: schema)
    monkeypatch.setattr(registry, "is_registered", lambda name: True)
    raw = _base(
        steps=[
            {"id": "up", "type": "agent", "prompt": "x"},
            {
                "id": "s",
                "type": "tool",
                "tool": "counter",
                "args": {"count": "${steps.up.output.n}"},
            },
        ]
    )
    wf = parse_definition(raw)  # no raise: literal type check deferred for mapped values
    assert wf.steps[1].args["count"] == "${steps.up.output.n}"


# ── placeholder syntax ────────────────────────────────────────────────────────


def test_unknown_placeholder_root_rejected():
    raw = _base(steps=[{"id": "a", "type": "notify", "text": "${env.HOME}"}])
    with pytest.raises(WorkflowDefinitionError, match="inputs|steps|env"):
        parse_definition(raw)
