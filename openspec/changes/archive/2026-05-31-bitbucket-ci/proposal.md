## Why

fleetent is now developed by multiple contributors in parallel. The repository already protects the
main branch through pull requests, but merge safety still depends on reviewers noticing whether the
full test suite has run.

This change adds a Bitbucket Pipelines CI gate so pull requests cannot be merged unless the project
unit test suite completes successfully.

## What Changes

- Add `bitbucket-pipelines.yml` at the repository root.
- Run CI for every pull request.
- Run the same test verification on updates to `main`.
- Set a non-secret `ANTHROPIC_API_KEY=test-key` value for test settings initialization.
- Install dependencies with `uv sync --frozen --group dev` so CI uses the checked-in lockfile.
- Initialize the SQLite schema with `uv run alembic upgrade head`.
- Run the full pytest suite with `uv run pytest`.

## Impact

- **Code**: no runtime code changes.
- **Configuration**: new Bitbucket Pipelines configuration.
- **Team workflow**: Bitbucket merge checks should require a successful build before merging PRs.
- **Future hardening**: ruff, mypy, and coverage thresholds can be added after the test gate is
  stable.
