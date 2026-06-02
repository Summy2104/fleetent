## Why

fleetent 已经具备 Google Drive / Confluence connector 的手动 sync API，但 Pilot 环境中 operator 还缺少统一的操作入口：

- 不知道当前配置了哪些 connector。
- 不方便验证 `credential_ref` 是否可用。
- 不方便 dry-run 查看本次会同步什么。
- 不方便查看最近一次同步是否成功、失败原因是什么。

如果排障仍然依赖写 Python 脚本或手动调用内部函数，Pilot 试用会很难交付给非核心开发者。本 change 增加最小 connector operations 边界，让 KB connector 可以通过 `fleetent-admin` CLI 被列出、检查、同步和查看状态。

## What Changes

- 从 `settings.yaml` 读取 Google Drive / Confluence connector 定义。
- 配置文件只保存 connector metadata 和 `credential_ref`，不保存真实 credential。
- 新增 connector registry / operations public API：
  - list configured connectors
  - get connector by `connector_id`
  - check credential / remote scope health
  - dry-run sync
  - run sync
  - read last connector status
- 新增 `fleetent-admin kb connectors ...` CLI：
  - `list`
  - `check <connector_id>`
  - `status <connector_id>`
  - `sync <connector_id> --dry-run`
  - `sync <connector_id>`
- 新增 knowledge-base-owned `knowledge_connector_status` 表，只保存每个 connector 最近一次运行摘要。
- sync 成功、失败或认证失败后更新最近一次 status。
- 输出 sync summary：scanned / planned / ingested / changed / unchanged / unsupported / archived / failed / auth_failed。
- 输出失败摘要时不显示 secret、token、完整文档正文或 connector credential 内容。
- 更新 knowledge-base、configuration、deployment 和 roadmap 文档。

## Out of Scope

- 不做 HTTP admin API。
- 不做 Admin UI / platform UI。
- 不做 scheduler、worker、queue 或后台自动同步。
- 不做完整 connector run history 或 item-level history。
- 不做 credential 创建、更新、轮换、加密存储或 secret manager。
- 不把真实 OAuth token、refresh token、client secret 或 Confluence API token 写入 `settings.yaml`。
- 不做 Google Drive / Confluence per-user ACL 映射。
- 不新增第三方 connector。

## Module Boundary Impact

- **Owning package**：`intelligence.knowledge_base` owns connector registry、operations 和 status store；
  `platform/admin CLI` 暴露操作入口。
- **Public API surface**：新增 connector operation dataclasses 和 functions，例如
  `list_configured_connectors()`、`get_connector_config()`、`check_connector()`、
  `run_connector_sync()`、`get_connector_status()`。
- **Owned tables**：新增 `knowledge_connector_status`。
- **Config namespace**：扩展 `knowledge_base.google_drive.connectors[]` 和
  `knowledge_base.confluence.connectors[]`；真实 credential 仍只通过 `credential_ref` 引用。
- **Cross-module dependencies**：admin CLI 调用 knowledge-base public operations API；operations API 复用现有
  Google Drive / Confluence connector public sync API、config 和 database runtime。
- **Migration / shim plan**：新增 additive CLI 子命令和 additive API；不移除现有 `sync_google_drive()` /
  `sync_confluence()` public API。
