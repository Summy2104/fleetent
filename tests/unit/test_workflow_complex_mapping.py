"""Complex mapping scenarios: deeply nested paths, mixed containers,
list indices, multiple placeholders in one string, and edge cases.
"""

import pytest

from fleetent.workflow.errors import WorkflowMappingError
from fleetent.workflow.mapping import extract_refs, render

_CONTEXT = {
    "inputs": {
        "channel": "#general",
        "config": {"mode": "auto", "retries": 3},
        "tags": ["a", "b", "c"],
    },
    "steps": {
        "extract": {
            "output": {
                "contract": {
                    "parties": [
                        {"name": "Acme", "role": "buyer", "contacts": [{"email": "a@a.com"}]},
                        {"name": "Beta", "role": "seller", "contacts": [{"email": "b@b.com"}]},
                    ],
                    "amount": 50000,
                    "terms": {"duration": "12m", "auto_renew": True},
                },
                "doc_no": "NS260429",
            }
        },
        "verify": {
            "output": {
                "verdict": "clean",
                "issues": [],
                "score": 95,
            }
        },
    },
}


# ── deeply nested dict path ──────────────────────────────────────────────────


def test_render_deeply_nested_dict_path():
    result = render("${steps.extract.output.contract.terms.duration}", _CONTEXT)
    assert result == "12m"


def test_render_nested_boolean_preserves_type():
    result = render("${steps.extract.output.contract.terms.auto_renew}", _CONTEXT)
    assert result is True


# ── list index access ────────────────────────────────────────────────────────


def test_render_list_index_zero():
    result = render("${steps.extract.output.contract.parties.0.name}", _CONTEXT)
    assert result == "Acme"


def test_render_list_index_one():
    result = render("${steps.extract.output.contract.parties.1.role}", _CONTEXT)
    assert result == "seller"


def test_render_nested_list_in_list():
    result = render("${steps.extract.output.contract.parties.0.contacts.0.email}", _CONTEXT)
    assert result == "a@a.com"


def test_render_input_list_index():
    result = render("${inputs.tags.1}", _CONTEXT)
    assert result == "b"


def test_render_list_index_out_of_range_fails():
    with pytest.raises(WorkflowMappingError, match="out of range"):
        render("${steps.extract.output.contract.parties.5.name}", _CONTEXT)


def test_render_negative_list_index_fails():
    with pytest.raises(WorkflowMappingError, match="out of range"):
        render("${steps.extract.output.contract.parties.-1.name}", _CONTEXT)


# ── entire container preserved as single placeholder ─────────────────────────


def test_render_entire_list_preserved():
    result = render("${steps.extract.output.contract.parties}", _CONTEXT)
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["name"] == "Acme"


def test_render_entire_dict_preserved():
    result = render("${steps.extract.output.contract.terms}", _CONTEXT)
    assert isinstance(result, dict)
    assert result["duration"] == "12m"


def test_render_entire_output_preserved():
    result = render("${steps.verify.output}", _CONTEXT)
    assert isinstance(result, dict)
    assert result["verdict"] == "clean"
    assert result["score"] == 95


# ── integer preserves type when single placeholder ───────────────────────────


def test_render_integer_preserved():
    result = render("${steps.extract.output.contract.amount}", _CONTEXT)
    assert result == 50000
    assert isinstance(result, int)


def test_render_integer_stringified_when_embedded():
    result = render("amount is ${steps.extract.output.contract.amount} USD", _CONTEXT)
    assert result == "amount is 50000 USD"


# ── multiple placeholders in one string ──────────────────────────────────────


def test_render_multiple_placeholders():
    result = render(
        "${steps.extract.output.doc_no}: ${steps.verify.output.verdict} "
        "(${steps.verify.output.score})",
        _CONTEXT,
    )
    assert result == "NS260429: clean (95)"


def test_render_placeholders_with_input_and_step():
    result = render("channel=${inputs.channel} doc=${steps.extract.output.doc_no}", _CONTEXT)
    assert result == "channel=#general doc=NS260429"


# ── nested input path ───────────────────────────────────────────────────────


def test_render_nested_input_dict():
    result = render("${inputs.config.mode}", _CONTEXT)
    assert result == "auto"


def test_render_nested_input_integer():
    result = render("${inputs.config.retries}", _CONTEXT)
    assert result == 3


# ── recursive rendering in dicts and lists ───────────────────────────────────


def test_render_recursive_dict():
    template = {
        "doc": "${steps.extract.output.doc_no}",
        "verdict": "${steps.verify.output.verdict}",
        "parties": "${steps.extract.output.contract.parties}",
    }
    result = render(template, _CONTEXT)
    assert result["doc"] == "NS260429"
    assert result["verdict"] == "clean"
    assert isinstance(result["parties"], list)


def test_render_recursive_list():
    template = [
        "${steps.extract.output.doc_no}",
        "${steps.verify.output.score}",
        "literal",
    ]
    result = render(template, _CONTEXT)
    assert result == ["NS260429", 95, "literal"]


def test_render_deeply_nested_template():
    template = {
        "report": {
            "header": "Doc: ${steps.extract.output.doc_no}",
            "details": {
                "buyer": "${steps.extract.output.contract.parties.0.name}",
                "amount": "${steps.extract.output.contract.amount}",
            },
            "tags": ["${inputs.tags.0}", "${inputs.tags.2}"],
        }
    }
    result = render(template, _CONTEXT)
    assert result["report"]["header"] == "Doc: NS260429"
    assert result["report"]["details"]["buyer"] == "Acme"
    assert result["report"]["details"]["amount"] == 50000
    assert result["report"]["tags"] == ["a", "c"]


# ── container stringified when embedded ──────────────────────────────────────


def test_render_list_stringified_when_embedded():
    result = render("issues: ${steps.verify.output.issues}", _CONTEXT)
    assert result == "issues: []"


def test_render_dict_stringified_when_embedded():
    result = render("terms: ${steps.extract.output.contract.terms}", _CONTEXT)
    assert "12m" in result
    assert "auto_renew" in result


# ── extract_refs finds all refs in complex structures ────────────────────────


def test_extract_refs_from_nested_structure():
    value = {
        "text": "hi ${inputs.channel}",
        "details": ["${steps.a.output.x}", {"nested": "${steps.b.output.y}"}],
    }
    refs = extract_refs(value)
    assert "inputs.channel" in refs
    assert "steps.a.output.x" in refs
    assert "steps.b.output.y" in refs


# ── fail-closed on missing paths ─────────────────────────────────────────────


def test_render_missing_input_key_fails():
    with pytest.raises(WorkflowMappingError, match="not found"):
        render("${inputs.nonexistent}", _CONTEXT)


def test_render_missing_nested_key_fails():
    with pytest.raises(WorkflowMappingError, match="not found"):
        render("${steps.extract.output.contract.nonexistent}", _CONTEXT)


def test_render_descend_into_scalar_fails():
    with pytest.raises(WorkflowMappingError, match="cannot descend"):
        render("${steps.extract.output.doc_no.substring}", _CONTEXT)


def test_render_unknown_step_fails():
    with pytest.raises(WorkflowMappingError, match="unknown step"):
        render("${steps.ghost.output.x}", _CONTEXT)


# ── no placeholders passthrough ──────────────────────────────────────────────


def test_render_no_placeholder_returns_same():
    assert render("plain text", _CONTEXT) == "plain text"
    assert render(42, _CONTEXT) == 42
    assert render(None, _CONTEXT) is None
    assert render(True, _CONTEXT) is True
