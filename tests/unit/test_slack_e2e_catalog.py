"""Unit: 能力覆盖清单的结构校验（字段完整、id 唯一、core 有 rubric、分组合法）。"""

from __future__ import annotations

import pytest

from tests.e2e.slack_autonomous.catalog import CATALOG, validate_catalog


def test_catalog_passes_its_own_validator() -> None:
    validate_catalog(CATALOG)  # 不抛异常即通过


def test_ids_are_unique() -> None:
    ids = [e["id"] for e in CATALOG]
    assert len(ids) == len(set(ids))


def test_core_entries_have_a_rubric() -> None:
    for e in CATALOG:
        if e["layer"] == "core":
            assert e.get("rubric"), f"core entry {e['id']} lacks a rubric"


def test_groups_are_partitioned_abc() -> None:
    assert {e["group"] for e in CATALOG} <= {"A", "B", "C"}


def test_layers_are_core_or_explore() -> None:
    assert {e["layer"] for e in CATALOG} <= {"core", "explore"}


def test_has_file_dependent_entries() -> None:
    # 文件收发是本套件的增量价值，清单必须包含依赖文件的功能点
    assert any(e.get("needs_file") for e in CATALOG)


def test_validator_rejects_duplicate_id() -> None:
    bad = [
        {
            "id": "x",
            "name": "n",
            "category": "c",
            "layer": "core",
            "group": "A",
            "trigger": "t",
            "rubric": "r",
            "needs_file": None,
            "preconditions": [],
        },
        {
            "id": "x",
            "name": "n2",
            "category": "c",
            "layer": "core",
            "group": "A",
            "trigger": "t",
            "rubric": "r",
            "needs_file": None,
            "preconditions": [],
        },
    ]
    with pytest.raises(ValueError):
        validate_catalog(bad)


def test_validator_rejects_core_without_rubric() -> None:
    bad = [
        {
            "id": "y",
            "name": "n",
            "category": "c",
            "layer": "core",
            "group": "A",
            "trigger": "t",
            "rubric": "",
            "needs_file": None,
            "preconditions": [],
        },
    ]
    with pytest.raises(ValueError):
        validate_catalog(bad)
