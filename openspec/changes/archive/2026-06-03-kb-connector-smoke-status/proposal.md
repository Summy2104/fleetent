## Why

Knowledge Base 的真实价值依赖企业知识源。当前 Google Drive / Confluence connector 已有 baseline 和
operations CLI，但 Pilot 前需要把 `check`、`dry-run sync`、`execute sync` 和 `latest status` 的证据格式、
真实 smoke opt-in 规则和 credential 安全边界固定下来。

## What Changes

- 强化 KB connector smoke/status：fake 默认测试 + real opt-in smoke。
- 真实 smoke 默认只做 `check + dry-run`；真实 `execute sync` 需要额外 opt-in flag，且只允许对明确标记的
  Pilot fixture folder / space 执行。
- latest status 输出 source scope、last check/sync、失败摘要、跳过原因和 redacted credential_ref。
- 将 connector smoke/status 纳入 pilot verification gate。

## Capabilities

### New Capabilities

- `kb-connector-smoke-status`: KB 数据源 connector smoke、dry-run、execute sync 和 latest status 证据契约。

## Impact

- **owning package**：`intelligence.knowledge_base`，管理入口经 `platform.admin_cli.kb_connectors`。
- **public API surface**：可扩展 connector operations CLI/status DTO；不暴露 credential payload。
- **owned tables**：如已有 connector state 表则复用；如缺 latest status 持久化，可新增/扩展 connector status store。
- **config namespace**：新增 real execute opt-in flag（例如 `FLEETENT_KB_CONNECTOR_EXECUTE_SMOKE=1`）。
- **cross-module dependencies**：依赖 KB public sync planner/executor、connector config/status public API、observability diagnostics。
- **migration / shim plan**：若新增 status 字段，经 Alembic 管理。

## Non-Goals

- 不实现 scheduler / worker / full sync history。
- 不实现 document-level ACL。
- 不默认执行真实 sync。
- 不管理真实 OAuth 授权流；只验证 credential_ref 前置条件。

## Strategy Defaults for Review

- Real smoke default: `check + dry-run` only.
- Real `execute sync`: requires separate explicit opt-in flag and Pilot fixture folder / space.
- Status output may show source metadata and redacted credential_ref, never credential payload.
