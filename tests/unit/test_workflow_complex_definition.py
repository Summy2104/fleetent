"""Complex workflow definition validation: multi-layer DAGs, mixed types,
deeply nested placeholders, large step counts, and edge cases in the
definition parser that basic tests don't cover.
"""

import pytest

from fleetent.workflow.definition import WorkflowDefinitionError, parse_definition


@pytest.fixture(autouse=True)
def _stub_registry(monkeypatch):
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
        },
        "calculate": {
            "type": "function",
            "function": {
                "name": "calculate",
                "parameters": {
                    "type": "object",
                    "properties": {"expression": {"type": "string"}},
                    "required": ["expression"],
                },
            },
        },
        "get_current_time": {
            "type": "function",
            "function": {
                "name": "get_current_time",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
    }
    monkeypatch.setattr(registry, "get_schema", lambda name: schemas.get(name))
    monkeypatch.setattr(registry, "is_registered", lambda name: name in schemas)


# ── diamond DAG parses without error ─────────────────────────────────────────


def test_diamond_dag_parses():
    wf = parse_definition(
        {
            "name": "diamond",
            "steps": [
                {"id": "a", "type": "agent", "prompt": "start"},
                {"id": "b", "type": "agent", "prompt": "use ${steps.a.output.text}"},
                {"id": "c", "type": "agent", "prompt": "use ${steps.a.output.text}"},
                {
                    "id": "d",
                    "type": "agent",
                    "prompt": "merge ${steps.b.output.x} ${steps.c.output.y}",
                    "depends_on": ["b", "c"],
                },
            ],
        }
    )
    assert len(wf.steps) == 4
    assert "b" in wf.control_deps["d"]
    assert "c" in wf.control_deps["d"]
    assert "a" in wf.control_deps["b"]
    assert "a" in wf.control_deps["c"]


# ── implicit data-ref deps cover all branches ───────────────────────────────


def test_data_ref_implies_deps_across_diamond():
    wf = parse_definition(
        {
            "name": "implicit",
            "steps": [
                {"id": "root", "type": "agent", "prompt": "x"},
                {"id": "left", "type": "agent", "prompt": "${steps.root.output.a}"},
                {"id": "right", "type": "agent", "prompt": "${steps.root.output.b}"},
                {
                    "id": "join",
                    "type": "notify",
                    "text": "${steps.left.output.x} ${steps.right.output.y}",
                },
            ],
        }
    )
    assert wf.control_deps["left"] == frozenset({"root"})
    assert wf.control_deps["right"] == frozenset({"root"})
    assert wf.control_deps["join"] == frozenset({"left", "right"})


# ── mixed type steps parse correctly ─────────────────────────────────────────


def test_mixed_type_chain_parses():
    wf = parse_definition(
        {
            "name": "mixed",
            "inputs": {"query": {"type": "string", "default": "hello"}},
            "steps": [
                {"id": "fetch", "type": "tool", "tool": "web_fetch", "args": {}},
                {
                    "id": "analyze",
                    "type": "agent",
                    "prompt": "analyze ${steps.fetch.output.body}",
                    "output_schema": {
                        "type": "object",
                        "required": ["summary"],
                    },
                },
                {
                    "id": "report",
                    "type": "notify",
                    "text": "Result: ${steps.analyze.output.summary}",
                    "to": {"platform": "slack", "target": "C1"},
                },
            ],
        }
    )
    assert wf.steps[0].type == "tool"
    assert wf.steps[1].type == "agent"
    assert wf.steps[2].type == "notify"
    assert wf.steps[1].output_schema is not None


# ── deeply nested placeholder syntax is valid ────────────────────────────────


def test_deeply_nested_placeholder_parses():
    wf = parse_definition(
        {
            "name": "deep",
            "steps": [
                {"id": "extract", "type": "agent", "prompt": "x"},
                {
                    "id": "use",
                    "type": "agent",
                    "prompt": "buyer=${steps.extract.output.contract.parties.0.name}",
                },
            ],
        }
    )
    assert "extract" in wf.control_deps["use"]


# ── multi-layer DAG: A→B→D, A→C→E, D+E→F ──────────────────────────────────


def test_multi_layer_dag_parses():
    wf = parse_definition(
        {
            "name": "multi",
            "steps": [
                {"id": "a", "type": "agent", "prompt": "x"},
                {"id": "b", "type": "agent", "prompt": "x", "depends_on": ["a"]},
                {"id": "c", "type": "agent", "prompt": "x", "depends_on": ["a"]},
                {"id": "d", "type": "agent", "prompt": "x", "depends_on": ["b"]},
                {"id": "e", "type": "agent", "prompt": "x", "depends_on": ["c"]},
                {"id": "f", "type": "agent", "prompt": "x", "depends_on": ["d", "e"]},
            ],
        }
    )
    assert wf.control_deps["f"] == frozenset({"d", "e"})
    assert wf.control_deps["d"] == frozenset({"b"})
    assert wf.control_deps["b"] == frozenset({"a"})


# ── larger step count parses ─────────────────────────────────────────────────


def test_large_fan_out_parses():
    steps = [{"id": "root", "type": "agent", "prompt": "x"}]
    for i in range(20):
        steps.append(
            {
                "id": f"w{i}",
                "type": "agent",
                "prompt": f"worker {i} uses ${{steps.root.output.text}}",
            }
        )
    steps.append(
        {
            "id": "merge",
            "type": "agent",
            "prompt": "merge all",
            "depends_on": [f"w{i}" for i in range(20)],
        }
    )
    wf = parse_definition({"name": "big-fan", "steps": steps})
    assert len(wf.steps) == 22
    assert len(wf.control_deps["merge"]) == 20


# ── complex cycle detection ──────────────────────────────────────────────────


def test_indirect_cycle_via_three_steps_rejected():
    with pytest.raises(WorkflowDefinitionError, match="cycle"):
        parse_definition(
            {
                "name": "tri-cycle",
                "steps": [
                    {"id": "a", "type": "agent", "prompt": "${steps.c.output.text}"},
                    {"id": "b", "type": "agent", "prompt": "${steps.a.output.text}"},
                    {"id": "c", "type": "agent", "prompt": "${steps.b.output.text}"},
                ],
            }
        )


def test_cycle_via_mixed_depends_on_and_data_ref():
    with pytest.raises(WorkflowDefinitionError, match="cycle"):
        parse_definition(
            {
                "name": "mixed-cycle",
                "steps": [
                    {"id": "a", "type": "agent", "prompt": "x", "depends_on": ["c"]},
                    {"id": "b", "type": "agent", "prompt": "${steps.a.output.text}"},
                    {"id": "c", "type": "agent", "prompt": "x", "depends_on": ["b"]},
                ],
            }
        )


# ── multiple inputs with mixed required/optional ────────────────────────────


def test_multiple_inputs_parsed():
    wf = parse_definition(
        {
            "name": "multi-input",
            "inputs": {
                "channel": {"type": "string"},  # required
                "mode": {"type": "string", "default": "auto"},
                "verbose": {"type": "boolean", "default": False},
            },
            "steps": [
                {
                    "id": "work",
                    "type": "agent",
                    "prompt": "ch=${inputs.channel} mode=${inputs.mode}",
                },
            ],
        }
    )
    assert wf.inputs["channel"].required is True
    assert wf.inputs["mode"].required is False
    assert wf.inputs["mode"].default == "auto"
    assert wf.inputs["verbose"].default is False


# ── tool args with placeholders: type check deferred ─────────────────────────


def test_tool_args_mixed_literal_and_placeholder():
    wf = parse_definition(
        {
            "name": "tool-mix",
            "steps": [
                {"id": "prep", "type": "agent", "prompt": "x"},
                {
                    "id": "calc",
                    "type": "tool",
                    "tool": "calculate",
                    "args": {"expression": "${steps.prep.output.expr}"},
                },
            ],
        }
    )
    assert wf.steps[1].args["expression"] == "${steps.prep.output.expr}"


# ── retry config parsing ────────────────────────────────────────────────────


def test_retry_config_parsed():
    wf = parse_definition(
        {
            "name": "retry-cfg",
            "steps": [
                {
                    "id": "flaky",
                    "type": "agent",
                    "prompt": "x",
                    "retry": {"max_attempts": 3},
                },
            ],
        }
    )
    assert wf.steps[0].max_attempts == 3


def test_invalid_retry_config_rejected():
    with pytest.raises(WorkflowDefinitionError, match="max_attempts"):
        parse_definition(
            {
                "name": "bad-retry",
                "steps": [
                    {
                        "id": "s",
                        "type": "agent",
                        "prompt": "x",
                        "retry": {"max_attempts": -1},
                    },
                ],
            }
        )


# ── timeout_seconds validation ───────────────────────────────────────────────


def test_custom_timeout_parsed():
    wf = parse_definition(
        {
            "name": "timeout",
            "steps": [
                {"id": "s", "type": "agent", "prompt": "x", "timeout_seconds": 60},
            ],
        }
    )
    assert wf.steps[0].timeout_seconds == 60


def test_zero_timeout_rejected():
    with pytest.raises(WorkflowDefinitionError, match="timeout"):
        parse_definition(
            {
                "name": "bad-to",
                "steps": [
                    {"id": "s", "type": "agent", "prompt": "x", "timeout_seconds": 0},
                ],
            }
        )


def test_boolean_timeout_rejected():
    with pytest.raises(WorkflowDefinitionError, match="timeout"):
        parse_definition(
            {
                "name": "bad-to",
                "steps": [
                    {"id": "s", "type": "agent", "prompt": "x", "timeout_seconds": True},
                ],
            }
        )


# ── unknown top-level field rejected ─────────────────────────────────────────


def test_unknown_top_level_field_rejected():
    with pytest.raises(WorkflowDefinitionError, match="version"):
        parse_definition(
            {
                "name": "bad",
                "version": "1.0",
                "steps": [{"id": "s", "type": "agent", "prompt": "x"}],
            }
        )


# ── notify step with deeply nested to ───────────────────────────────────────


def test_notify_with_complex_to_parses():
    wf = parse_definition(
        {
            "name": "notify-complex",
            "steps": [
                {
                    "id": "n",
                    "type": "notify",
                    "text": "hello",
                    "to": {
                        "platform": "slack",
                        "target": "C123",
                        "target_type": "channel",
                    },
                },
            ],
        }
    )
    assert wf.steps[0].to == {
        "platform": "slack",
        "target": "C123",
        "target_type": "channel",
    }


# ── placeholder in nested tool args ──────────────────────────────────────────


def test_placeholder_in_nested_list_args():
    wf = parse_definition(
        {
            "name": "nested-args",
            "inputs": {"sheet_id": {"type": "string"}},
            "steps": [
                {"id": "extract", "type": "agent", "prompt": "x"},
                {
                    "id": "write",
                    "type": "tool",
                    "tool": "web_fetch",
                    "args": {
                        "url": "https://example.com/${inputs.sheet_id}/${steps.extract.output.id}",
                    },
                },
            ],
        }
    )
    assert "${inputs.sheet_id}" in wf.steps[1].args["url"]
    assert "extract" in wf.control_deps["write"]
