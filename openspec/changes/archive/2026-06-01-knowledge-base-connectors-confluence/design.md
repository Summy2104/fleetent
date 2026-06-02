## Context

当前 KB 已经具备：

- `tenant_id + kb_id` 隔离。
- parser：plain text、Markdown、lightweight HTML。
- local directory connector 和 sync planner。
- `knowledge_source_states` 用于判断 new / changed / unchanged / missing。
- `ingest_parsed()` / `delete()` / `search()` public API。

Confluence connector 应复用这些边界，不能把 remote connector 写成绕过 planner 的特殊路径。

## Authentication

MVP 只支持 Confluence Cloud API token：

- `base_url`
- `username`
- API token via `credential_ref`

语义：

- credential 属于 connector，不属于最终提问用户。
- connector 只能同步该 API token 有权限访问的 configured space / page scope。
- 如果某个用户能访问同步后的 KB，就能检索该 KB 中的内容；MVP 不做 per-user Confluence ACL 过滤。
- token 无效、权限不足或 Confluence API 返回授权失败时，connector 进入 `auth_failed` 状态，等待重新配置 credential。

credential 存储：

- 使用 `credential_ref` 引用 API token。MVP 可以是环境变量引用或本地 secret 文件引用。
- 后续可以迁移到 SQLite credential store、secret manager 或 encryption at rest。
- 不提交真实 username、API token 或授权文件。

## Connector Scope

Confluence connector config 至少包含：

- `connector_id`
- `tenant_id`
- `kb_id`
- `base_url`
- `username`
- API token `credential_ref`
- scope type：`space` 或 `page`
- `space_key` 或 `page_id`
- `include_children`

范围语义：

- `space_key`：同步该 space 中的 pages。
- `page_id`：只同步指定 page。
- `page_id + include_children`：同步指定 page 及其 descendant pages。

MVP 不做全站扫描。

## Supported Content

支持：

- Confluence page storage HTML。
- page title、space key、ancestors / path text 作为 metadata。
- version / modified time 作为 change detection 输入。

暂不支持：

- attachment。
- comment / inline comment。
- blog post。
- whiteboard / database。
- Confluence page ACL 映射。

unsupported 内容应计入 summary，不应导致整次 sync 失败。

## Sync Planning

Confluence source state 使用 remote identity：

- `source_id`：connector id。
- `source_path`：建议使用 `confluence://{page_id}`。
- page id。
- space key。
- version / modified time。
- title。
- ancestors / path text。
- document_id。
- archived / missing 状态。

planner 动作：

- `ingest_new`：source state 不存在。
- `reingest_changed`：version 或 modified time 变化。
- `skip_unchanged`：source state 与 remote metadata 一致。
- `archive_missing`：source state 存在，但当前 scope listing 不再包含，或授权账号不再可见。
- `auth_failed`：API token 无效、权限不足或 Confluence authorization 失败。

`archive_missing` 不调用 KB physical delete。归档后的 document / chunks 默认不参与 search。实现阶段可以通过
document metadata、source state 状态或 search filter 实现，但必须可测试。

## Execution

executor 只按 plan 执行：

- new / changed：拉取 storage HTML，parse，调用 `ingest_parsed()`。
- unchanged：不 parse，不 ingest。
- archive_missing：标记 archived / missing，不物理删除 KB document。
- item 失败：记录 failed，继续处理其他 items。

Confluence API 网络错误或 rate limit 不应导致已成功 item 回滚。

## Rate Limit And Retry

MVP 应支持基础 rate limit / retry：

- connector config 支持 `requests_per_minute`。
- 遇到 429 且返回 Retry-After 时遵守 Retry-After。
- 其他 transient error 可以有限重试。
- 超过重试上限后记录 item failure 或 connector failure，不阻塞已完成 item。

## Testing

默认测试必须用 fake Confluence client：

- fake space page listing。
- fake page listing with pagination。
- fake page children traversal。
- fake page fetch with storage HTML。
- fake auth failure。
- fake 429 / retry-after。

默认测试不得访问真实 Confluence。

真实 smoke test 只能在显式环境变量开启时运行，例如：

- `FLEETENT_CONFLUENCE_SMOKE=1`
- Confluence base URL / username / credential_ref / space or page scope 环境变量齐全

缺少任意凭据时真实 smoke 必须 skip。

## Non-Goals

本 change 不解决：

- 文档级 ACL。
- agent 到多个 KB 的绑定策略。
- sync scheduler / worker。
- sync run history。
- attachments / comments / blog posts。
- Confluence Server / Data Center。
- Google Drive connector。
- Confluence 双向写回。
