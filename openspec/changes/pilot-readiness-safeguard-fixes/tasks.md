## 1. Config validation secret source fix

- [ ] 1.1 Write failing tests: env-provided provider / IM tokens do not make `validate-config --profile pilot` fail.
- [ ] 1.2 Write failing tests: secret-like values inside config files are still reported as errors with field paths.
- [ ] 1.3 Implement: scan config-file sources separately from resolved `Settings`, and keep env-backed secrets redacted.
- [ ] 1.4 Verify green: run `uv run pytest tests/unit/test_config_validation.py tests/integration/test_pilot_readiness_admin.py -x -q`.

## 2. KB connector execute sync gate

- [ ] 2.1 Write failing tests: `fleetent-admin kb connectors sync <id>` without `--dry-run` exits before mutation unless execute safeguards are present.
- [ ] 2.2 Write failing tests: execute sync succeeds only with `--yes`, execute opt-in env flag and `--pilot-fixture`.
- [ ] 2.3 Implement: add CLI gate and clear skip/error messages without changing dry-run behavior.
- [ ] 2.4 Verify green: run `uv run pytest tests/integration/test_pilot_readiness_admin.py tests/unit/test_pilot_readiness_reports.py -x -q`.

## 3. Maintenance trace evidence

- [ ] 3.1 Write failing tests: maintenance apply records an observability trace event and returns its trace reference.
- [ ] 3.2 Write failing tests: dry-run maintenance does not record mutation trace evidence.
- [ ] 3.3 Implement: record trace evidence through observability public API for manual maintenance apply commands.
- [ ] 3.4 Verify green: run `uv run pytest tests/integration/test_pilot_readiness_admin.py -x -q`.

## 4. Documentation and final checks

- [ ] 4.1 Write failing docs/check tests if applicable: Pilot docs show execute sync safeguards accurately.
- [ ] 4.2 Implement: update Pilot runbook, install checklist and acceptance guide command examples.
- [ ] 4.3 Run `uv run ruff format src tests`.
- [ ] 4.4 Run `uv run ruff check src tests`.
- [ ] 4.5 Run `uv run pytest -x -q`.
- [ ] 4.6 Run `openspec validate pilot-readiness-safeguard-fixes`.
