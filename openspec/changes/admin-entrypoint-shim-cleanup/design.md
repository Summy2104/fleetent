## Context

`fleetent.platform.admin_cli.main` now owns parser construction and command dispatch. The top-level
`fleetent.admin` module is a thin compatibility shim:

```python
from fleetent.platform.admin_cli.main import main
```

The remaining compatibility surface is:

- `pyproject.toml` console script: `fleetent-admin = "fleetent.admin:main"`
- `tests/integration/test_admin.py`: imports `from fleetent import admin`
- roadmap and active module-boundaries specs describing `fleetent.admin.main` as supported

## Target State

The canonical entrypoint is the only first-party admin CLI import path:

```python
from fleetent.platform.admin_cli.main import main
```

Packaging metadata routes the installed command directly:

```toml
fleetent-admin = "fleetent.platform.admin_cli.main:main"
```

`fleetent.admin` is deleted and must raise `ModuleNotFoundError`.

## Implementation Strategy

1. Add failing tests that assert the console script metadata points to
   `fleetent.platform.admin_cli.main:main` and `fleetent.admin` cannot be imported.
2. Update admin tests to call `admin_cli_main` directly.
3. Update pyproject and delete `src/fleetent/admin.py`.
4. Update roadmap docs and active spec delta language.

Existing integration tests for `fleetent-admin` commands are the behavior-preservation gate. This change
must not touch command implementation modules except where a test import target changes.

## Risks

- If tests keep importing the shim, deleting `fleetent.admin` will fail before behavior is checked.
- If only tests are updated but `pyproject.toml` remains old, installed `fleetent-admin` would break.
- Console script metadata needs a direct assertion because calling `admin_cli_main` in tests is not enough
  to prove packaging changed.

## Verification

- Red step: run `uv run pytest tests/unit/test_admin_entrypoint_cleanup.py -x -q` and observe failure
  because pyproject still points at `fleetent.admin:main` and/or `fleetent.admin` is importable.
- Green step: rerun that test after implementation.
- Run `uv run pytest tests/integration/test_admin.py -x -q`.
- Run module boundary check, ruff format/check, mypy, full pytest, strict OpenSpec validation, and
  `git diff --check`.
