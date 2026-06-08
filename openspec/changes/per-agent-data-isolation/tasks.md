## 1. paths.py — agent_data_dir

- [x] 1.1 Write failing tests for `paths.agent_data_dir()`: derive from `agents_dir()`, injectable via monkeypatch
- [x] 1.2 Add `agent_data_dir(agent_id: str) -> Path` to `src/fleetent/paths.py`

## 2. agent_app.boot() — data path redirection

- [x] 2.1 Write failing tests for `boot()` path redirection: sessions, DB URL default, approvals, diagnostics
- [x] 2.2 Implement `_redirect_agent_data_paths(home_dir)` helper in `agent_app.py` and call it from `boot()` before `_start_infra()`

## 3. Log directory — resolve blank to agent home

- [x] 3.1 Write failing tests: blank `observability.logging.directory` → resolves to `home_dir/data/logs/`; explicit path → used as-is
- [x] 3.2 Update `_configure_logging_from_agent()` to resolve blank directory to `home_dir / "data" / "logs"`
- [x] 3.3 Update `ObservabilitySettings.logging.directory` default from `"data/logs"` to `""` in `src/fleetent/config.py`
- [x] 3.4 Update `agents/default/agent.yaml.example` `observability.logging.directory` comment

## 4. Full test suite green

- [x] 4.1 Run `uv run pytest -x -q` and fix any regressions
