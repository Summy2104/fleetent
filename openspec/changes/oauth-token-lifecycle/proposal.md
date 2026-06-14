## Why

P0 把 OAuth 授权码凭证存进 `external_credentials` 并打通首次 consent，但 access token 会过期、refresh token 会失效、用户/管理员需要主动吊销——这些**生命周期**未做。本变更补齐 token 自动刷新、过期与失效的状态流转、以及凭证吊销，使长期运行的 agent 不会因 token 过期而静默失败。

> Apply 顺序：依赖 `external-credential-vault`（P0）先 archive。

## What Changes

- **access token 自动刷新**：解析凭证时若 access token 已过期且持有有效 refresh token，SHALL 先刷新再返回 `Credential`；刷新成功更新密文与过期时间。
- **状态流转**：refresh token 失效 → `status=needs_reauth`（解析返回 `NeedsConsent`）；刷新网络失败（可重试）→ `status=error`（解析返回可重试错误，区别于未授权）。
- **凭证吊销**：提供 revoke，删除本地凭证并尽力调用 provider 的 revoke endpoint；吊销后该 principal 下次使用回到 `NeedsConsent`。
- **刷新/吊销不泄漏**：token 明文 MUST NOT 进日志 / trace / 异常文本。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `external-credential-vault`: 新增 token 刷新、过期/失效状态流转、凭证吊销三组要求（以 ADDED 形式扩展 vault 能力）。

## Impact

- **owning package**：`platform/connector_management`（Vault provider 的刷新/吊销逻辑、凭证 store 的状态列更新）。
- **public API surface**：`get_credential` 行为扩展（过期自动刷新；失效返回 `NeedsConsent`/可重试错误）——契约形状不变；新增 revoke store 函数。
- **owned tables**：无新增（`external_credentials` 复用 `status` 列与密文列）。
- **config namespace**：无（刷新阈值如需可配，落既有配置面，不新增命名空间）。
- **cross-module dependencies**：刷新/吊销全在 platform 侧 provider；agent runtime 仅经 seam 只读取凭证；不碰 agent⊥platform。外部 HTTP（token endpoint / revoke endpoint）测试用 `respx` mock。
- **migration / shim plan**：无 schema 迁移。
- **不在范围**：后台定时批量刷新守护（按需另议）；API-key 协议无 refresh 概念（P3）；admin 的 lifecycle 可观测视图（P5）。
