## 1. CI configuration

- [x] 1.1 Add a Bitbucket Pipelines configuration for pull requests.
- [x] 1.2 Set `ANTHROPIC_API_KEY=test-key` for test settings initialization.
- [x] 1.3 Install dependencies with `uv sync --frozen --group dev`.
- [x] 1.4 Initialize the SQLite schema with `uv run alembic upgrade head`.
- [x] 1.5 Run the full unit test suite with `uv run pytest`.
- [x] 1.6 Run the same verification on `main` branch updates.

## 2. Verification

- [x] 2.1 Validate the pipeline YAML syntax locally.
- [x] 2.2 Run the project test command locally.
- [x] 2.3 Confirm Bitbucket merge checks require a successful build.
