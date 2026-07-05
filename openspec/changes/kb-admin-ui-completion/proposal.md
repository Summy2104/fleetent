# kb-admin-ui-completion

## Why

前端 KB 管理页（`frontend/src/features/kb`）目前只覆盖 KB 增删改、文档列删、只读查看绑定 agents——管理员验证 KB 是否好用的核心工具（检索 playground）、绑定/解绑操作、chunk 预览、文档上传都缺，而对应的后端 API 全部现成（上传端点由 kb-ingest-upload-path 提供）。补齐这四件后，"KB 在 Platform 侧可简单管理"在 UI 层闭环。

## What Changes

- **检索 playground**：KB 详情内提供查询框，调 `POST /admin/kb/search`，展示命中 chunk（内容、得分、来源文档）。
- **绑定/解绑操作**：现有只读 agents 视图升级为可操作——绑定（agent 候选来自既有 agents API）调 `POST /admin/kb/{kb_id}/agents`，解绑调 `DELETE /admin/kb/{kb_id}/agents/{agent_id}`。
- **chunk 预览**：文档列表项展开调 `GET /admin/kb/{kb_id}/documents/{document_id}/chunks`，展示分块内容与 section 上下文。
- **文档上传框**：multipart 调 `POST /admin/kb/{kb_id}/documents`（kb-ingest-upload-path 的代理端点），成功展示 job id 提示 + 手动刷新文档列表。
- **kb-admin-ui spec 修订**：既有 requirement 明文禁止 SPA 出现 ingest 控件并断言不调 `POST /admin/kb/{id}/documents`（retired）——该封条随上传端点在 kb-ingest-upload-path 复活而解除，本 change 用 MODIFIED 重写该 requirement；connector 管理与目录同步**仍不进 SPA**。
- **不做**：评估触发与观测面板（API 已有，UI deferred）；不改任何后端代码。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `kb-admin-ui`：SPA 支持的 KB 能力面从"CRUD + 文档列删 + 只读绑定"扩展为含 playground、绑定操作、chunk 预览、文档上传；撤销"SPA 不调文档上传端点"的断言（connector/目录同步不进 SPA 的约束保留）。

## Impact

- **Owning package**：`frontend/src/features/kb`（`api.ts` / `page.tsx` / 测试），纯前端。
- **Public API surface**：无后端变更；SPA 新消费 4 个既有/新增端点（search、agents 绑定两个、chunks、upload）。
- **Owned tables / Config namespace / Migration**：均无。
- **Cross-module dependencies**：agent 候选列表复用既有 agents feature 的 API 模块（前端内部复用）。
- **依赖顺序**：上传框依赖 kb-ingest-upload-path 的 `POST /admin/kb/{kb_id}/documents` 已合 main；playground/绑定/chunks 三件不依赖，可先行实现。
