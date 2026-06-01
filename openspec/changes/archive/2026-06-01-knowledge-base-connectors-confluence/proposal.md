## Why

fleetent 当前 knowledge-base 已支持 local directory 手动同步、sync planner、parser、hybrid retrieval 和 reindex source
iterator，但还没有接入真实企业知识源。Randy 公司同时使用 Google Drive 和 Confluence，因此除
`knowledge-base-connectors-google-drive` 外，还需要定义 Confluence connector。

knowledge-bridge 已验证 Confluence Cloud 的 `base_url + username + api_token` 路径，并支持按 space、page、
page children 同步。fleetent 应迁移这条已验证路径的设计经验，但继续遵守 fleetent 的 SQLite-first、无 AI 框架依赖、
sync planner、KB public API 和 remote connector 安全边界。

## What Changes

- 增加 Confluence connector，支持 Confluence Cloud API token 认证。
- 使用 `credential_ref` 引用 API token 凭据，不把真实 token 写入 connector config。
- 支持同步范围：
  - `space_key`
  - `page_id`
  - `page_id + include_children`
- 同步结果写入指定 `tenant_id + kb_id`。
- 拉取 Confluence storage HTML，并走现有 HTML parser。
- 通过 sync planner 生成 plan，再执行 plan，不边扫描边写 KB。
- 源端 missing / 不可见时默认 `archive_missing` / `mark_missing`，不物理删除 KB document。
- 默认不做 Confluence per-user / per-page ACL 映射；访问控制继续依赖 `tenant_id + kb_id` 和后续 agent-KB 绑定。
- 默认测试使用 fake Confluence client / fixtures，不连接真实 Confluence。
- 真实 Confluence smoke test 只能通过显式环境变量手动开启。

## Out of Scope

- 不做 Confluence Server / Data Center、Basic Auth、PAT 分支或多认证模式。
- 不做最终提问用户到 Confluence page ACL 的实时映射。
- 不做附件、评论、inline comment、whiteboard、database 或其他 Confluence 非 page 内容。
- 不做 webhook、scheduler、worker、sync run history 或动态 job runtime。
- 不做 Admin UI。
- 不物理删除 missing document；物理删除策略后续单独讨论。

## Module Boundary Impact

- **Owning package**：`intelligence.knowledge_base`。
- **Public API surface**：新增 Confluence connector config、`credential_ref`、Confluence data source、
  planning / sync public API。
- **Owned tables**：复用或扩展 `knowledge_source_states` 记录 page id、space key、version / modified time、
  ancestors / path text、archived / missing 状态；MVP 不强制新增 credential 表。
- **Config namespace**：`knowledge_base.confluence.*`。
- **Cross-module dependencies**：依赖 config / database runtime；通过 existing HTML parser、sync planner、
  `ingest_parsed()` 和 KB public API 写入；不绕过 vector_store 或 KB core。
- **Migration / shim plan**：无 legacy Confluence connector；新增能力。
