## ADDED Requirements

### Requirement: Frontend quality gate runs in PR pipeline

The project SHALL gate the `frontend/` workspace in the same PR pipeline as the Python suite. A `make test-frontend` target SHALL run the frontend unit/component tests (Vitest), a TypeScript type check (`tsc --noEmit`), and lint; the PR build SHALL fail when any of them fails. The frontend SHALL enforce a unit-test coverage threshold that the gate fails below.

#### Scenario: PR runs frontend checks

- **WHEN** a pull request touches the repository
- **THEN** the CI pipeline installs the frontend dependencies from the checked-in `yarn.lock`
- **AND** runs `make test-frontend` (Vitest with coverage threshold + `tsc --noEmit` + lint)
- **AND** fails the build if any frontend test, the type check, lint, or the coverage threshold fails

#### Scenario: Frontend coverage threshold is enforced

- **WHEN** the frontend unit tests run in CI with coverage
- **THEN** coverage is measured over `frontend/src`
- **AND** the gate fails when total frontend coverage is below the configured threshold

#### Scenario: Runtime stays Node-free

- **WHEN** the project is packaged for deployment
- **THEN** the frontend is built to static assets (`frontend/dist`) at build/CI time
- **AND** the deployed runtime serves those static assets via FastAPI with no Node process
