# kb-admin-ui-completion — Tasks

> 纯前端 change。每个实现 task 严格红绿：先写 vitest 测试（`cd frontend && yarn vitest run <file>` 见红）→ 实现 → 同命令见绿。测试任务在对应实现任务之前。
> 前三组不依赖其他 change；第 4 组（上传框）前置 = kb-ingest-upload-path 已合 main。

## 1. chunk 预览

- [x] 1.1 测试：`api.ts` 新增 chunks 查询 hook（`GET /admin/kb/{id}/documents/{doc}/chunks`，mock fetch 断言路径与解包）（先红）
- [x] 1.2 实现：chunks hook；见绿
- [x] 1.3 测试：文档列表项可展开分块预览，展示 chunk 内容与 section 上下文（testing-library，先红）
- [x] 1.4 实现：Documents 区展开预览 UI；见绿

## 2. 绑定/解绑操作

- [x] 2.1 测试：`api.ts` 新增 bind/unbind mutation（`POST /admin/kb/{id}/agents`、`DELETE /admin/kb/{id}/agents/{agent_id}`），成功后 invalidate 绑定列表（先红）
- [x] 2.2 实现：绑定 mutations；见绿
- [x] 2.3 测试：Agents 区——候选 agent 下拉（复用既有 agents API 模块）+ 绑定提交刷新列表 + 已绑定行的解绑操作（先红）
- [x] 2.4 实现：Agents 区操作 UI；见绿

## 3. 检索 playground

- [x] 3.1 测试：`api.ts` 新增 search mutation（`POST /admin/kb/search`，载荷含 kb_id/query，可选 top_k）（先红）
- [x] 3.2 实现：search mutation；见绿
- [x] 3.3 测试：Playground 区——查询提交后按得分展示命中 chunk（内容、得分、来源文档名）；空结果与请求失败有明确文案（先红）
- [x] 3.4 实现：Playground UI；见绿

## 4. 文档上传框（前置：kb-ingest-upload-path 已合 main）

- [x] 4.1 测试：`api.ts` 新增 upload mutation（multipart `POST /admin/kb/{id}/documents`），413/404 错误路径抛出可辨识错误（先红）
- [x] 4.2 实现：upload mutation；见绿
- [x] 4.3 测试：上传框 UI——成功展示"已入队（job <id>）"提示与手动刷新入口；413/404 展示错误不误报成功（先红）
- [x] 4.4 实现：上传框 UI；见绿

## 5. 收尾

- [x] 5.1 全量前端门禁：`cd frontend && yarn test`（vitest + coverage）与 lint 通过，coverage 无回落
- [x] 5.2 change/PR 收尾：`make test-pr` + `make test-integration-ci`（后端零改动，判据=无新增失败）
