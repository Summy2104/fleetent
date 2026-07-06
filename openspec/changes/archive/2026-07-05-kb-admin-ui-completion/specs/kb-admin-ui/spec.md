# kb-admin-ui — Delta

## MODIFIED Requirements

### Requirement: Knowledge Base managed natively in the React SPA

The React admin SPA SHALL render the Knowledge Base domain natively (not a deep-link to legacy) and SHALL support, against the existing admin API: list / create / edit / delete knowledge bases; list and delete documents; **preview a document's chunks** (`GET /admin/kb/{id}/documents/{doc}/chunks`, content + section context); **upload a document** (`POST /admin/kb/{id}/documents`, multipart — 成功提示 job id 并支持手动刷新文档列表); **manage agent bindings**（查看之外可绑定 / 解绑，`POST /admin/kb/{id}/agents` / `DELETE /admin/kb/{id}/agents/{agent_id}`，agent 候选复用既有 agents API）; and a **retrieval playground**（`POST /admin/kb/search`，展示命中 chunk 的内容、得分与来源文档）。

The SPA SHALL NOT expose KB connector management or directory-sync controls — connector 真相源留在 KB 服务侧 `connectors.yaml`（`kb-standalone-ingest`）。评估触发与观测面板不在本要求范围（deferred）。

#### Scenario: List and create knowledge bases

- **WHEN** an admin opens the KB view
- **THEN** knowledge bases are listed via `GET /admin/kb`, and creating one calls `POST /admin/kb` and refreshes the list

#### Scenario: List and remove documents

- **WHEN** an admin views a KB's documents or deletes one
- **THEN** the SPA calls `GET /admin/kb/{id}/documents` (resp. `DELETE /admin/kb/{id}/documents/{doc}`) and the document list refreshes

#### Scenario: 预览文档分块
- **WHEN** 管理员展开某文档的分块预览
- **THEN** SPA 调 `GET /admin/kb/{id}/documents/{doc}/chunks` 并展示每个 chunk 的内容与 section 上下文

#### Scenario: 上传文档并异步入库
- **WHEN** 管理员在 KB 详情选择文件上传
- **THEN** SPA 以 multipart 调 `POST /admin/kb/{id}/documents`，成功后提示已入队（含 job id）；刷新文档列表后（worker 消费完成）该文档出现

#### Scenario: 上传错误反馈
- **WHEN** 上传返回 413（超限）或 404（KB 不存在）
- **THEN** SPA 展示对应错误信息，不误报成功

#### Scenario: 绑定与解绑 agent
- **WHEN** 管理员在 KB 的 Agents 区选择一个 agent 绑定，或对已绑定 agent 解绑
- **THEN** SPA 分别调 `POST /admin/kb/{id}/agents` / `DELETE /admin/kb/{id}/agents/{agent_id}` 并刷新绑定列表

#### Scenario: 检索 playground
- **WHEN** 管理员在 playground 输入查询词提交
- **THEN** SPA 调 `POST /admin/kb/search` 并按得分展示命中 chunk（内容、得分、来源文档）

#### Scenario: Connector 与目录同步不在 SPA
- **WHEN** the KB view is rendered
- **THEN** there is no Connectors tab and no directory-sync control
- **AND** the SPA makes no calls to `/admin/kb/connectors…` or `POST /admin/kb/{id}/sync`

#### Scenario: KB no longer deep-links to legacy

- **WHEN** the SPA navigation is rendered
- **THEN** Knowledge Base is a native route, not an entry in the legacy deep-link list
