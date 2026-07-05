# kb-admin-ui-completion — Design

## Context

`frontend/src/features/kb` 现为单页模式（`page.tsx` + `api.ts` + vitest/testing-library 测试），react-query 管数据。后端 API 全数就绪：`POST /admin/kb/search`（playground）、`POST/DELETE /admin/kb/{kb_id}/agents[/{agent_id}]`（绑定）、`GET .../chunks`（预览）、`POST /admin/kb/{kb_id}/documents`（上传，来自 kb-ingest-upload-path）。前端 CI 是 per-merge 门禁之一（vitest + coverage）。

## Goals / Non-Goals

**Goals:**

- 管理员在 SPA 内完成"建库 → 上传 → 看分块 → playground 验证检索 → 绑 agent"的完整操作闭环，不再需要 CLI/curl。
- 保持既有单页信息架构与代码风格（react-query hooks 在 `api.ts`、视图在 `page.tsx` 体系内），不引入新路由框架/状态库。

**Non-Goals:**

- 评估触发、观测面板（deferred）。
- connector 管理、目录同步控件（spec 明确继续排除）。
- 上传进度条/job 轮询（成功即提示 job id，手动刷新列表）。

## Decisions

**D1 — 信息架构：KB 详情区内加 tab/分区（Documents / Agents / Playground），不拆子路由。**
与现有单页模式一致，改动面最小；文档上传框与 chunk 预览挂在 Documents 区，绑定操作挂在 Agents 区。替代方案——按功能拆独立路由页：与仓库其他 feature 的组织方式不一致，拒绝。

**D2 — playground 最小参数面：query 输入 + 可选 top_k（默认后端值），结果按得分排序展示 chunk 内容与来源文档名。**
不暴露 mode/rerank 等调优旋钮（属后端 retrieval policy 与评估工具的职责）；管理员用它回答"这库能不能搜到"，不是调参台。

**D3 — 绑定操作的 agent 候选复用既有 agents feature 的列表 API 模块，不新写请求层。**
前端内部复用，保持单一数据获取路径。

**D4 — 上传不做轮询：成功 toast 展示 job id + 文档列表提供手动刷新。**
与 kb-ingest-upload-path 设计（admin API 不封装轮询）对齐；异步 ingest 的完成信号靠刷新后文档出现。替代方案——前端定时 refetch：对慢 ingest 空转请求，且掩盖失败（job 失败列表永远不出现），拒绝。

**D5 — 测试策略：每个新区块一组 vitest + testing-library 测试（mock fetch/api 层），红绿节奏与后端 TDD 纪律一致；上传框错误路径（413/404）必须有断言。**

## Risks / Trade-offs

- **[上传后"什么都没发生"的观感]** ingest 异步，刷新前列表不变。→ Mitigation：成功提示明确写"已入队（job <id>），处理完成后出现在文档列表"；文案进测试断言。
- **[前端 coverage 门禁]** 新增代码量较大，测试不足会拖低 coverage。→ Mitigation：D5 每区块配测；收尾以 `yarn test`（vitest run --coverage）本地过为准。
- **[与 kb-ingest-upload-path 的时序]** 上传框依赖后端端点。→ Mitigation：tasks 把上传框排最后一组并注明前置；前三件可在该 change 未合时先行。

## Migration Plan

纯前端，无迁移。上传框上线前若后端端点未部署，操作得 404——tasks 顺序约束已避免该窗口。回滚 = 回退前端版本。

## Open Questions

- 评估触发与观测面板的 UI 形态（表格 or 图表）——deferred，等本轮四件落地后按使用反馈立项。
