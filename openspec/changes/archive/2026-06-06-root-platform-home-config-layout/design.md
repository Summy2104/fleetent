## Decisions

### D1 — repo root / `FLEETENT_HOME` is Platform home

The Platform home is the deployment root. In local development the repository root may act as
Platform home; in installed deployments `FLEETENT_HOME` is Platform home.

Canonical runtime layout:

```text
<platform-home>/
  .env
  platform.yaml
  agents/
    <agent-id>/
      agent.yaml
      .env
      data/
  data/
  secrets/
```

Canonical example layout:

```text
.env.example
platform.yaml.example
agents/
  default/
    agent.yaml.example
    .env.example
```

`config/` SHALL NOT contain canonical config/env templates after this change.

### D2 — `.example` lives beside the real file it templates

Every submitted example mirrors its runtime instance path:

- `.env.example` templates `.env`.
- `platform.yaml.example` templates `platform.yaml`.
- `agents/default/agent.yaml.example` templates `agents/default/agent.yaml`.
- `agents/default/.env.example` templates `agents/default/.env`.

This removes the indirection `config/platform/.env.example -> .env` and
`config/agent/agent.yaml.example -> agents/default/agent.yaml`.

### D3 — Platform config owns embedded Knowledge construction

Default MVP deployment keeps Knowledge embedded in the Platform service. Therefore KB construction
config (`knowledge_bases[]`, sources, indexing, sync, remote endpoint mode) belongs in Platform
config / Platform DB. The default runtime SHALL NOT read or materialize
`<FLEETENT_HOME>/config/knowledge.yaml`.

Agent config continues to own only Agent-side KB visibility and retrieval:

```yaml
knowledge:
  enabled: true
  bindings:
    - tenant_id: pilot-tenant
      kb_id: pilot-kb
      default: true
  retrieval_policy:
    mode: hybrid
```

### D4 — ENV boundaries remain Platform vs Agent

Platform `.env` contains Platform process variables such as `FLEETENT_SECRET_KEY`,
`DATABASE_URL`, `FLEETENT_TUI_URL`, `FLEETENT_TOKEN`, `LOG_FORMAT`, and embedded Platform
service credentials when those services run in the Platform process.

Agent `.env` contains only variables referenced by that Agent runtime's `agent.yaml` and
materialized credential slots. Platform DB variables, Platform master secret, and Platform-owned
KB construction credentials SHALL NOT be written into Agent `.env`.

### D5 — DB remains the authoring source where it already exists

`platform.yaml` is a bootstrap/importable Platform file view, not a replacement for existing DB
authoring paths. Existing DB-backed areas keep their DB source of truth:

- model providers and routes
- Agent definitions and bindings
- Agent credential slots / injected secrets
- KB connector definitions and Agent-KB bindings
- owner-level IM connector config

Implementation may use `platform.yaml.example` as seed/documentation and may load `platform.yaml`
for local file-mode defaults, but it must not introduce a second conflicting source of truth for
DB-managed state.

### D6 — legacy root `agent.yaml` single-file mode is retired

The supported default Agent runtime lives under `agents/default/`. Root `agent.yaml` was an
intermediate layout and conflicts with Platform home semantics. Because this is MVP and not
launched, this change removes the old default root-agent path from docs/specs/tests rather than
maintaining compatibility.
