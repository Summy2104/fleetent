# Proposal: agent-yaml-intelligence-config

## Why

The deployment configuration contract has moved toward a self-contained `agent.yaml` plus `.env` model. The global `config/settings.yaml.example` template has been removed, but intelligence configuration still needs a documented, schema-validated place in the agent template so operators can configure vector store, embedding, rerank, knowledge base, and long-term context without relying on a removed settings template.

## What Changes

- Extend the `agent.yaml` schema to accept typed intelligence configuration blocks:
  - `vector_store`
  - `embedding`
  - `rerank`
  - `knowledge_base`
  - `long_term_ctx`
- Reuse the existing `Settings` submodels for those blocks so field names and validation stay aligned with current intelligence settings.
- Update `config/agent.yaml.example` with non-secret intelligence configuration migrated from the local `settings.yaml` shape.
- Keep secrets as env-var references only.

## Non-Goals

- Do not switch intelligence runtime initialization from `Settings()` to agent config in this change.
- Do not restore `config/settings.yaml.example`.
- Do not inline any API key, OAuth token, refresh token, or client secret.

## Module Boundary Impact

- owning package: `runtime` / file agent configuration boundary, with schema types reused from `config`.
- public API surface: `fleetent.agent_config.AgentFile` gains optional typed fields for intelligence config.
- owned tables: none.
- config namespace: agent file adds `vector_store`, `embedding`, `rerank`, `knowledge_base`, and `long_term_ctx` blocks.
- cross-module dependencies: `agent_config` imports existing typed settings models from `fleetent.config`; runtime consumers are unchanged.
- migration / shim plan: local `config/settings.yaml` remains backward-compatible as an optional override while templates move to `agent.yaml.example`.
