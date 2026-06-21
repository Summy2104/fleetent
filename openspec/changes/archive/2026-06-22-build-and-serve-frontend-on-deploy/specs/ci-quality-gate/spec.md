## ADDED Requirements

### Requirement: CI verifies the frontend build, not just tests

The CI frontend gate SHALL run `make frontend-build` (a real `vite build`) in addition to tests/typecheck/lint, so a build-time breakage (e.g. asset/import resolution that `tsc` and `vitest` do not catch) fails the build rather than only surfacing at deploy time.

#### Scenario: Build breakage fails CI

- **WHEN** the frontend `vite build` fails (while `tsc`/`vitest` might still pass)
- **THEN** the CI frontend gate fails the build

#### Scenario: Successful build passes

- **WHEN** `make frontend-build` produces `frontend/dist` without error
- **THEN** the build step passes and the deployable artifact is confirmed buildable
