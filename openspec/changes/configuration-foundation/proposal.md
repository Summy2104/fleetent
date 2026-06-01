## Why

fleetent currently mixes configuration sources: `.env` drives `Settings`, while MCP, cron, and webhook
definitions are loaded from separate YAML files. The architecture docs already describe `.env +
config/settings.yaml`, but the runtime has not implemented that contract. As more modules add
configuration, keeping multiple ad hoc files will make deployment, review, and on-premises support harder.

## What Changes

- Add `config/settings.yaml` as the single non-secret application configuration file.
- Keep `.env` for secrets and environment-specific overrides; environment variables override YAML values.
- Move deployment-level MCP server configuration into `settings.yaml` under `mcp.servers`.
- Remove `config/mcp.yaml`, `config/cron.yaml`, and `config/webhooks.yaml` runtime loading.
- Do not move cron jobs into YAML. Scheduled tasks remain runtime objects stored in SQLite.
- Do not move webhook sources into YAML. Webhook source management will be handled by a later dedicated
  change; this change only keeps webhook global policy in settings.
- Update examples, docs, and tests to match the single settings file contract.

## Out of Scope

- No backward compatibility fallback for old YAML paths.
- No hot reload.
- No Admin UI configuration editor.
- No configuration center or database-backed dynamic config.
- No model router route migration.
- No cron job or webhook source management redesign beyond removing legacy YAML file loading.

## Impact

- **Code**: `fleetent.config`, server startup, MCP loading, cron scheduler startup, webhook startup.
- **Config files**: keep `config/settings.yaml.example`; remove old per-feature YAML examples.
- **Docs**: deployment, architecture, MCP, scheduling, and webhook-related capability docs.
- **Tests**: update config loading tests and path monkeypatches to use isolated `settings.yaml`.
