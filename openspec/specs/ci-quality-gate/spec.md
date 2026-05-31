# ci-quality-gate Specification

## Purpose
Define the repository CI gate that verifies pull requests and main branch updates with Bitbucket
Pipelines before code is accepted.

## Requirements
### Requirement: Pull requests run the full test suite

The project SHALL run Bitbucket Pipelines for pull requests and fail the build when the Python test
suite fails.

#### Scenario: Pull request executes unit tests

- **WHEN** a pull request is opened or updated
- **THEN** Bitbucket Pipelines sets test-only environment needed for settings initialization
- **AND** installs project dependencies from the checked-in lockfile
- **AND** initializes the SQLite schema with Alembic
- **AND** runs `uv run pytest`
- **AND** reports a failed build if any test fails

### Requirement: Main branch updates are verified

The project SHALL run the same unit test verification for commits that reach the `main` branch.

#### Scenario: Main branch executes unit tests

- **WHEN** a commit is merged into `main`
- **THEN** Bitbucket Pipelines sets test-only environment needed for settings initialization
- **AND** installs project dependencies from the checked-in lockfile
- **AND** initializes the SQLite schema with Alembic
- **AND** runs `uv run pytest`
- **AND** reports a failed build if any test fails
