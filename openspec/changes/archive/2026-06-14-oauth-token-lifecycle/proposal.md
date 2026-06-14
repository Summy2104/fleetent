## Why

P0/P1 已把 OAuth 凭证以 `external_credential_store.put_oauth_credential(...)` 写入 `external_credentials`，并由 `vault_provider.get_credential(...)` 经 `connectors.get_credential(...)` seam 解析，但当前实现仍是最小形态：payload 只是加密 JSON dict（现有真实字段来自 provider token 响应，如 `access_token` / `refresh_token` / `expires_in` / `scope`），store 只暴露 `put_oauth_credential` / `get_credential`，provider 只区分 `authorized` 与 `NeedsConsent`。access token 会过期、refresh token 会失效、用户/管理员也需要主动吊销——这些**生命周期**未做。本变更补齐 token 自动刷新、过期与失效的状态流转、以及凭证吊销，使长期运行的 agent 不会因 token 过期而静默失败。

> Apply 顺序：依赖 `external-credential-vault`（P0）先 archive。

## What Changes

- **access token 自动刷新**：解析凭证时若 access token 已过期且持有有效 refresh token，SHALL 先刷新再返回 `Credential`；刷新成功把新 token 负载回写到现有 `payload` JSON 中，并在该 payload 内维护标准化的 `expires_at`。
- **状态流转**：refresh token 失效 → `status=needs_reauth`（解析返回 `NeedsConsent`）；刷新网络失败（可重试）→ `status=error`（解析返回新的可重试错误结果，区别于未授权）。
- **凭证吊销**：提供 revoke，删除本地凭证并尽力调用 provider 的 revoke endpoint；吊销后该 principal 下次使用回到 `NeedsConsent`。
- **刷新/吊销不泄漏**：token 明文 MUST NOT 进日志 / trace / 异常文本。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `external-credential-vault`: 新增 token 刷新、过期/失效状态流转、凭证吊销三组要求（以 ADDED 形式扩展 vault 能力）。

## Impact

- **owning package**：`platform/connector_management`（Vault provider 的刷新/吊销逻辑、凭证 store 的状态列更新与删除）、`connectors.py` seam（新增可重试错误结果类型）。
- **public API surface**：`get_credential` 行为扩展（过期自动刷新；失效返回 `NeedsConsent`；网络刷新失败返回新的 retryable credential error）；`connectors.CredentialProvider` 从当前 `Credential | NeedsConsent` 扩到三态；`external_credential_store` 新增面向生命周期的辅助函数（保持现有 `put_oauth_credential` / `get_credential` 为基线）。
- **owned tables**：无新增（`external_credentials` 复用 `status` 列与密文列）。
- **config namespace**：无（刷新阈值如需可配，落既有配置面，不新增命名空间）。
- **cross-module dependencies**：刷新/吊销全在 platform 侧 provider/store；agent runtime 仅经 seam 读取 `Credential` / `NeedsConsent` / retryable error 结果；token/revoke endpoint 取自 `external_service_store.get_service(...)[\"oauth_config\"]`；不碰 agent⊥platform。外部 HTTP（token endpoint / revoke endpoint）测试用 `respx` mock。
- **migration / shim plan**：无 schema 迁移。
- **不在范围**：后台定时批量刷新守护（按需另议）；API-key 协议无 refresh 概念（P3）；admin 的 lifecycle 可观测视图（P5）。
