## Context

当前 KB 已经具备：

- `tenant_id + kb_id` 隔离。
- parser：plain text、Markdown、lightweight HTML。
- local directory connector 和 sync planner。
- `knowledge_source_states` 用于判断 new / changed / unchanged / missing。
- `ingest_parsed()` / `delete()` / `search()` public API。

Google Drive connector 应复用这些边界，不能把 remote connector 写成绕过 planner 的特殊路径。

## Authentication

MVP 使用 OAuth 用户授权。

语义：

- 每个 Google Drive connector 绑定一个 Google 账号授权。
- connector 只能同步该账号有权限访问的指定 folder。
- token / credential 属于 connector，不属于最终提问用户。
- 如果某个用户能访问同步后的 KB，就能检索该 KB 中的内容；MVP 不做 per-user Google Drive ACL 过滤。
- refresh token 失效或权限不足时，connector 进入 `auth_failed` 状态，等待重新授权。

credential 存储：

- 使用 `credential_ref` 引用 OAuth credential。MVP 可以是本地 token 文件路径，类似 knowledge-bridge 的
  `token_path`；后续可以迁移到 SQLite credential store、secret manager 或 encryption at rest。
- 如果使用本地 token 文件，文档必须说明生产部署需要保护文件权限和备份策略。
- 如果实现选择 SQLite 存储 token，必须通过 DB runtime / store 边界访问。
- 不提交真实 client secret、refresh token 或授权文件。

## Connector Scope

Google Drive connector config 至少包含：

- `connector_id`
- `tenant_id`
- `kb_id`
- `folder_id`
- OAuth `credential_ref`
- include / exclude patterns
- supported MIME types

MVP 只扫描指定 folder。是否递归扫描子目录可以配置，但默认建议开启递归，因为企业文档常按目录层级组织。

## Supported Content

支持：

- Google Docs：MVP export 为 HTML，调用现有 `parse_html()`。
- `text/plain`：调用 `parse_text()`。
- Markdown：按文件名或 MIME type 识别后调用 `parse_markdown()`。
- HTML：调用 `parse_html()`。

暂不支持：

- PDF。
- Office 文档。
- 图片、视频、压缩包。
- Google Sheets / Slides。

unsupported 文件应计入 summary，不应导致整次 sync 失败。

knowledge-bridge 已有 Google Docs / Sheets 结构化读取经验，但 fleetent MVP 先不引入该复杂度。Docs / Sheets
结构化解析作为后续增强独立设计。

## Sync Planning

Google Drive source state 使用 remote identity，而不是本地 path：

- `source_id`：connector id。
- `source_path`：建议使用 stable remote path 或 `drive://{file_id}`。
- remote file id。
- modified time。
- revision / version id（如果可用）。
- content hash（如果可计算）。
- document_id。
- archived / missing 状态。

planner 动作：

- `ingest_new`：source state 不存在。
- `reingest_changed`：modified time、revision 或内容 hash 变化。
- `skip_unchanged`：source state 与 remote metadata 一致。
- `archive_missing`：source state 存在，但当前 folder listing 不再包含，或授权账号不再可见。
- `skip_unsupported`：MIME type 不支持。
- `auth_failed`：token refresh 或 Drive API authorization 失败。

`archive_missing` 不调用 KB physical delete。归档后的 document / chunks 默认不参与 search。实现阶段可以通过
document metadata、source state 状态或 search filter 实现，但必须可测试。

## Execution

executor 只按 plan 执行：

- new / changed：读取或 export 内容，parse，调用 `ingest_parsed()`。
- unchanged：不 parse，不 ingest。
- unsupported：不 parse，不 ingest。
- archive_missing：标记 archived / missing，不物理删除 KB document。
- item 失败：记录 failed，继续处理其他 items。

Google API 网络错误不应导致已成功 item 回滚。

## Testing

默认测试必须用 fake Drive client：

- fake folder listing。
- fake file metadata。
- fake file download。
- fake Google Docs HTML export。
- fake token refresh failure。

默认测试不得访问真实 Google API。

真实 smoke test 只能在显式环境变量开启时运行，例如：

- `FLEETENT_GOOGLE_DRIVE_SMOKE=1`
- Google OAuth client / credential_ref / folder id 环境变量齐全

缺少任意凭据时真实 smoke 必须 skip。

## Non-Goals

本 change 不解决：

- 文档级 ACL。
- agent 到多个 KB 的绑定策略。
- sync scheduler / worker。
- sync run history。
- PDF / Office 解析。
- Confluence connector。
- Google Drive 双向写回。
