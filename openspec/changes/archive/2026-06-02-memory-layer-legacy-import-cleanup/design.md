## Context

`fleetent.intelligence.memory` now owns memory models, store access, extraction, search, operations, and
maintenance. The top-level `fleetent.memory_layer` module is a re-export shim.

Remaining first-party legacy imports appear in:

- integration tests for memory, reflection, long-term context, and retention/compaction
- unit tests for memory package imports, indexable items, retention/compaction, and reflection maintenance
- evaluation scripts for memory extraction, memory KB embedding, long-term context, and reflection reports
- roadmap and active specs that still describe `fleetent.memory_layer` compatibility

## Target State

Canonical imports are the only supported first-party memory boundary:

```python
from fleetent.intelligence import memory
from fleetent.intelligence.memory import MemoryItem, search, extract_and_update
```

`fleetent.memory_layer` is deleted and must raise `ModuleNotFoundError`.

## Implementation Strategy

1. Add failing tests that assert `fleetent.intelligence.memory` exposes the expected public API and
   `fleetent.memory_layer` cannot be imported.
2. Mechanically migrate tests and evaluation scripts to canonical imports.
3. Delete `src/fleetent/memory_layer.py`.
4. Update roadmap docs and spec delta language.

Do not edit memory implementation modules except if a test import target requires canonical package naming.
Existing memory tests cover behavior preservation across schema, extraction, search, retention,
compaction, reflection, vector reindex, and long-term context.

## Risks

- Some tests import `from fleetent import memory_layer` and then monkeypatch module globals. These must
  become `from fleetent.intelligence import memory` aliases so monkeypatches still target the real module.
- Evaluation scripts are not always part of full pytest, so import migration must include direct search
  verification across `tests/evaluation`.
- Active specs may continue requiring shim compatibility unless archive updates them.

## Verification

- Red step: run `uv run pytest tests/unit/test_memory_legacy_import_cleanup.py -x -q` and observe failure
  because `fleetent.memory_layer` is still importable.
- Green step: rerun that test after implementation.
- Run targeted memory, retention/compaction, reflection, long-term context, and evaluation import tests.
- Run module boundary check, ruff format/check, mypy, full pytest, strict OpenSpec validation, and
  `git diff --check`.
