# runtime-paths Delta Spec

## ADDED Requirements

### Requirement: Per-agent data directory accessor

`paths.py` SHALL expose `agent_data_dir(agent_id: str) -> Path` returning
`agents_dir() / agent_id / "data"`. This formalises the per-agent data root so callers
never construct it inline and the derivation is testable in isolation.

#### Scenario: agent_data_dir derives from agents_dir

- **WHEN** `paths.agent_data_dir("my-bot")` is called with `FLEETENT_HOME=/home/x/.fleetent`
- **THEN** it SHALL return `Path("/home/x/.fleetent/agents/my-bot/data")`

#### Scenario: agent_data_dir is injectable in tests

- **WHEN** a test monkeypatches `paths.agents_dir` to return a `tmp_path`
- **THEN** `paths.agent_data_dir("test-agent")` SHALL return `tmp_path / "test-agent" / "data"`
