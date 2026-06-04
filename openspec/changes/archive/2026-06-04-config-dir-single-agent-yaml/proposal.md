# Proposal: config-dir-single-agent-yaml

## Why

The deployed single-agent configuration is currently seeded and loaded from the Fleetent home root as `agent.yaml`, while the rest of local non-secret configuration lives under `config/`. Operators expect the concrete non-template agent config to live alongside other local config files as `config/agent.yaml`.

## What Changes

- Change the single-agent config path resolver from `base_dir()/agent.yaml` to `config_dir()/agent.yaml`.
- Update single-agent loading tests and wording from home-root to config-dir single file.
- Update install bootstrap to seed `$FLEETENT_HOME/config/agent.yaml` from `config/agent.yaml.example` while keeping `.env` at the home root.
- Update template comments to describe the new concrete path.
- Migrate the local ignored `agent.yaml` to ignored `config/agent.yaml`.

## Non-Goals

- Do not remove multi-agent `config/agents/<name>/agent.yaml` support.
- Do not change the `AgentFile` schema.
- Do not commit local concrete `config/agent.yaml`, `.env`, or `config/settings.yaml`.

## Module Boundary Impact

- owning package: `runtime` / path resolution and agent config loader.
- public API surface: `fleetent.paths.agent_file()` now returns `config/agent.yaml`.
- owned tables: none.
- config namespace: concrete single-agent config moves to `config/agent.yaml`.
- cross-module dependencies: install script and tests depend on the central path resolver contract.
- migration / shim plan: existing home-root `agent.yaml` is not the preferred path; local operator config should be moved to `config/agent.yaml`.
