## Why

fleetent 当前 knowledge-base 已支持 local directory 手动同步、sync planner、parser、hybrid retrieval 和 reindex source
iterator，但还没有接入真实企业知识源。Randy 当前公司更常用 Google Drive，因此第一批 remote connector 先做
Google Drive，而不是 Confluence。

本 change 目标是把指定 Google Drive folder 中的文档同步到指定 `tenant_id + kb_id`，复用现有 KB parser、
sync planner 和 ingest/search 边界，同时避免把 Google Drive 权限、OAuth token 和源端删除语义扩散到 KB core。

## What Changes

- 增加 Google Drive connector，按指定 `folder_id` 列举文档，不扫描整个 Drive。
- 使用 OAuth 用户授权，不做 service account 或 domain-wide delegation。
- OAuth token / credential 绑定到 connector，不绑定最终提问用户；credential 通过 `credential_ref` 引用，MVP 可指向本地 token 文件。
- 同步结果写入指定 `tenant_id + kb_id`。
- Google Docs MVP 通过 Drive export API 导出为 HTML 后走现有 HTML parser；Docs / Sheets 结构化解析后置。
- 支持文本类文件：plain text、Markdown、HTML，以及 Google Docs。
- unsupported MIME type 跳过并进入 sync summary，不阻塞其他文件。
- 源端 missing / 不可见时默认 `archive_missing` / `mark_missing`，不物理删除 KB document。
- 默认不做 Google Drive per-user ACL 映射；访问控制继续依赖 `tenant_id + kb_id` 和后续 agent-KB 绑定。
- 默认测试使用 fake Drive client / fixtures，不连接真实 Google API。
- 真实 Google Drive smoke test 只能通过显式环境变量手动开启。

## Out of Scope

- 不做 service account、domain-wide delegation 或 Google Workspace 管理员授权流程。
- 不做最终提问用户到 Google Drive 文档 ACL 的实时映射。
- 不做全盘扫描，只支持指定 folder scope。
- 不做 Shared Drive 的复杂组织治理语义；如果 folder 在 Shared Drive 中，MVP 只要求 API 能列举该 folder。
- 不做 PDF、Office、Google Sheets、Google Slides、图片、视频或 OCR / VLM 解析。
- 不做后台 scheduler、worker、sync run history 或动态 job runtime。
- 不做 Admin UI。
- 不物理删除 missing document；物理删除策略后续单独讨论。

## Module Boundary Impact

- **Owning package**：`intelligence.knowledge_base`。
- **Public API surface**：新增 Google Drive connector config、OAuth `credential_ref`、Google Drive data source、
  planning / sync public API。
- **Owned tables**：复用或扩展 `knowledge_source_states` 记录 remote file id、revision / modified time、
  content hash、archived / missing 状态；OAuth token 可由 `credential_ref` 指向本地 token 文件，MVP 不强制新增
  credential 表。
- **Config namespace**：`knowledge_base.google_drive.*`。
- **Cross-module dependencies**：依赖 config / database runtime；通过 existing parser、sync planner、`ingest_parsed()`
  和 KB public API 写入；不绕过 vector_store 或 KB core。
- **Migration / shim plan**：无 legacy Google Drive connector；新增能力。
