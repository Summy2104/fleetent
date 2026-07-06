"""Unit tests for runtime ${...} field-mapping rendering (pure logic)."""

import pytest

from fleetent.workflow.errors import WorkflowMappingError
from fleetent.workflow.mapping import render

_CTX = {
    "inputs": {"channel": "#reports", "n": 3},
    "steps": {
        "fetch": {"output": {"text": "ok", "items": [{"id": 1}, {"id": 2}], "count": 5}},
        "analyze": {"output": {"summary": "done"}},
    },
}


def test_single_placeholder_preserves_type():
    assert render("${steps.fetch.output.count}", _CTX) == 5
    assert render("${inputs.n}", _CTX) == 3
    assert render("${steps.fetch.output.items.0.id}", _CTX) == 1


def test_single_placeholder_preserves_container():
    assert render("${steps.fetch.output.items}", _CTX) == [{"id": 1}, {"id": 2}]


def test_embedded_placeholder_stringifies_container():
    out = render("items=${steps.fetch.output.items}", _CTX)
    assert out == 'items=[{"id": 1}, {"id": 2}]'


def test_embedded_multiple_placeholders():
    out = render("summary=${steps.analyze.output.summary} n=${inputs.n}", _CTX)
    assert out == "summary=done n=3"


def test_nested_dict_and_list_rendered():
    val = {"to": "${inputs.channel}", "meta": ["${steps.fetch.output.count}", "lit"]}
    # single-placeholder list item preserves type (int 5), literal passes through
    assert render(val, _CTX) == {"to": "#reports", "meta": [5, "lit"]}


def test_literal_without_placeholder_passthrough():
    assert render("https://example.com", _CTX) == "https://example.com"
    assert render(42, _CTX) == 42


def test_missing_key_fails_closed():
    with pytest.raises(WorkflowMappingError, match="missing"):
        render("${steps.fetch.output.missing}", _CTX)


def test_index_out_of_range_fails_closed():
    with pytest.raises(WorkflowMappingError, match="range"):
        render("${steps.fetch.output.items.9.id}", _CTX)


def test_unknown_step_fails_closed():
    with pytest.raises(WorkflowMappingError, match="ghost"):
        render("${steps.ghost.output.x}", _CTX)


def test_unknown_root_fails_closed():
    with pytest.raises(WorkflowMappingError, match="root"):
        render("${env.HOME}", _CTX)
