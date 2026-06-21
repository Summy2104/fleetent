## Context

④ 已在 main 提供平台 ingress:`POST /admin/agents/{agent_name}/chat`(`server.py:553`,流式响应,经 `_require_admin_session`)与 `@app.websocket("/admin/agents/{agent_name}/ws")`(`server.py:568`,经 `authorization` header 认证)。C1 SPA 壳的港域范式(`features/agents/`:`api.ts`+`page.tsx`+`page.test.tsx`,域在 `routes.tsx` 三处登记)已坐实。本切片在此之上加运维对话页。

## Goals / Non-Goals

**Goals:** 运维在 SPA 选 agent → 对话/调试托管 agent,流式渲染回复,不可达有明确反馈;TDD + MSW。
**Non-Goals:** 不改 ④ 的 ingress;不做浏览器双向 WS;不做端用户聊天入口;不引入新依赖。

## Decisions

**D1 · 浏览器走 `POST /chat` 流式,不走 WS。**
④ 的 `/ws` 从 `authorization` **header** 取 admin token,而**浏览器原生 WebSocket 不能设自定义 header**——所以 SPA 用 `POST /admin/agents/{name}/chat`(fetch 能带 Authorization header)并**读 `ReadableStream` 增量渲染**。`/ws` 留给能设 header 的非浏览器客户端(如 TUI)。若日后要浏览器双向 WS,需 ④ 补 query-param / `Sec-WebSocket-Protocol` 认证——属后端跟进,不在本切片。

**D2 · 消费 SSE 事件协议,不是裸文本(已对照 ④ 实现核实)。**
④ 的 `agent_transport.chat` 用 `stream=True` + `StreamingResponse` 原样代理 agent `/chat` 的 SSE 流(`media_type` 默认 `text/event-stream`)。流的内容是 `data:` 行、JSON `{type, content}`,`type` ∈ `text_delta`(追加)/ `done`(收尾)/ `error`(显示错误)——实测 demobot 即 `data:{"type":"text_delta",...}` → `data:{"type":"done",...}`。所以前端必须**解析 SSE 事件**,不能把字节当纯文本拼接。

**D3 · 流式状态自管,不套 TanStack Query。**
对话是流式追加,不是可缓存查询。用自管 hook:fetch `POST /chat`(带 Authorization,复用现有 admin 认证)→ 读 response body reader → 按 SSE 切 `data:` 事件 → 据 `type` 更新消息状态(text_delta 追加 / done 收尾 / error 显示);切 agent 或离开页面时 abort fetch。agent 列表选择器仍用 TanStack Query(`GET /admin/agents`)。

**D4 · 不可达明确反馈(已对照 ④ 状态码)。**
`_resolve_agent_node_id`:未知 agent → **404**、无 placement → **503**;upstream≥400 → ④ 回 buffered Response 带状态码。前端据状态码渲染"该 agent 当前不可达",据流内 `error` 事件渲染运行期错误——都不空转、不卡死。

**D5 · routes.tsx 唯一共享缝。** 注册 chat(import + NavLink + Route);`routes.test.tsx` 断言用 `within(nav)` scope。⑤⑥⑦ 已落地、Connectors 也已原生,本 change 现在是**唯一**在动 `routes.tsx` 的前端切片,无并发竞争;**合并由主会话串行做**(窗口只实现 + push 分支,不自行 `git checkout main && merge`)——这是上一轮 routes.tsx 对撞事故后的固定规则。

## Risks / Trade-offs

- **[误以为该用 WS]** → D1 已记录浏览器 header 限制;选 POST 流式是浏览器侧正确解,WS 留后端跟进。
- **[流式读取兼容/中断]** → 处理 reader 提前结束 / abort(切换 agent 或离开页面时 abort fetch)、SSE 事件跨 chunk 截断的缓冲拼接;测试覆盖 text_delta/done/error/abort。
- **[SSE 解析]** → 按 `\n\n` 切事件、`data:` 取 JSON;容忍 keep-alive 空行与跨 chunk 半行。
- **[把后端 ingress 的认证缺口当前端 bug]** → 明确:浏览器 WS 不可达是 ④ 认证形态所致,非本页 bug;已在 D1/Non-Goals 记录。
