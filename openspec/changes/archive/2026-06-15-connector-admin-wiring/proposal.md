## Why

`oauth-connector-admin` 描述的 per-user 授权矩阵、admin 吊销、offboarding 联动、凭证生命周期可观测，在现状里全是 placeholder（`connectors_list_grants` 返回 `[]`、`connectors_revoke` 返回 `wired:False` 等）。P0–P4 把真实凭证库与生命周期建起来后，本变更把这些 placeholder **接到真 Vault**，并按 P0/P2 的模型把规格里的「per-agent 范围」改为「per-(user, service) / status 来自 vault」。

> Apply 顺序：依赖 `external-credential-vault`（P0）；矩阵/吊销/lifecycle 的完整语义还依赖 `oauth-token-lifecycle`（P2，提供 status 流转与 revoke）；offboarding 与 `user-blocklist`/用户停用联动。建议在 P2 之后 apply。

## What Changes

- **per-user 授权矩阵接 vault**：`(user, service)` 每格状态来自 `external_credentials.status`（authorized / not_authorized / needs_reauth / error），**去掉 owning-agent 范围**（承接 P0 单层全局）。
- **admin 吊销接 vault**：触发 P2 的 revoke（删本地凭证 + 尽力外部 revoke），需确认 + 落审计；吊销后用户回到 `NeedsConsent`。
- **offboarding 联动**：用户被停用时，展示「该用户所有外部凭证被自动吊销」的结果（哪些成功/失败），供下线审计。
- **生命周期可观测**：每服务展示 token 刷新成功/失败率与因 refresh 失效导致的重新授权次数（数据源自 P2）。
- **全视图遮蔽**：`client_secret`、access/refresh token 在所有视图与审计中遮蔽。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `oauth-connector-admin`: 把「Per-user authorization matrix」「Admin revoke on behalf of a user」「Offboarding linkage visibility」「Credential lifecycle observability」四组要求从 per-agent 范围/placeholder 改为 per-(user, service)、状态/吊销来自 Vault。

## Impact

- **owning package**：`platform/connector_management`（`connectors_list_grants` / `connectors_revoke` / `connectors_offboarding_result` / `connector_lifecycle_stats` 由 placeholder 接 Vault）。
- **public API surface**：上述 4 个 seam 函数从「placeholder 返回空/未接线」改为「查 Vault / 触发 revoke」；端点形状不变。
- **owned tables**：无新增（读 `external_credentials`）。
- **config namespace**：无。
- **cross-module dependencies**：纯 platform 管理面；不被 agent runtime import。offboarding 与用户停用（`user-blocklist`/user-center）联动，经 platform 内部调用。
- **migration / shim plan**：无 schema 迁移。
- **不在范围**：矩阵的 UI 呈现细节（前端）；后台批量刷新守护。
