> 前端 TDD 硬门禁:先写测试见红 → 实现见绿。最窄 `yarn --cwd frontend vitest run <file>`。测试先于实现。照 C1 `features/agents/` 范式。⑤⑥⑦ 已落地,本 change 是当前唯一动 `routes.tsx` 的前端切片;**合并由主会话串行做(窗口只实现 + push 分支,不自行 checkout main && merge)**。

## 1. 流式数据层(api.ts,TDD)

- [x] 1.1 写测试(Vitest+MSW):`useAgentsQuery`(选择器,`GET /admin/agents`)+ 流式发送 hook——`POST /admin/agents/{name}/chat` 带 Authorization,**按 SSE 解析** `data:` 事件(`{type,content}`):`text_delta` 增量产出、`done` 收尾、`error` 产出错误;覆盖跨 chunk 半行拼接、abort;不可达(404/503)产出清晰错误。先见红。
- [x] 1.2 实现 `features/chat/api.ts`(agent 列表用 TanStack Query;对话用自管流式 hook,fetch + reader + SSE 解析,切换 agent/离开时 abort)。跑 1.1 见绿。

## 2. 页面(page.tsx,TDD)

- [x] 2.1 写测试(`page.test.tsx`,MSW):选 agent → 发消息 → `text_delta` 事件增量渲染到对话区、`done` 收尾、`error` 事件显示在对话里;不可达(404/503)显示"agent unavailable"不卡死;空/加载态。先见红。
- [x] 2.2 实现 `features/chat/page.tsx`(agent 选择器 + 对话面板 + 流式渲染 + 错误提示)。跑 2.1 见绿。

## 3. 路由注册(共享缝)

- [x] 3.1 在 `app/routes.tsx` 注册 chat(import + nav NavLink + Route);补 `routes.test.tsx` 断言(用 `within(nav)` scope)。

## 4. Change 收尾验证

- [x] 4.1 `make test-frontend` 全绿(vitest + 覆盖率阈值 + tsc --noEmit + lint)。
- [x] 4.2 `make test-pr` 全绿(对照 main 基线无新增失败)。
- [ ] 4.3 手动核对(需 ④ 在线 + 一个 placement 的 agent):`/admin/ui` 内 chat 页选 agent、发消息、看到流式回复;选未 placement 的 agent 显示明确不可达提示。
