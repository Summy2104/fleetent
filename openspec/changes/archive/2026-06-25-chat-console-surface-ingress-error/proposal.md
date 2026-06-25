## Why

Web 控制台对 agent 发消息失败时,前端 `toIngressError`(`frontend/src/features/chat/api.ts:37`)把 ingress `POST /admin/agents/{name}/chat` 的**任何 503** 都显示成固定文案 `Agent "X" is unavailable because it has no active placement.`。但 ingress 503 实际涵盖多种原因——`node 'X' service key unavailable`(密钥解不出)、上游流式错误(`str(exc)`)、真正的无 placement——后端已在响应体 `{detail: ...}` 里给出准确原因,前端却丢弃它、一律归因到 placement。2026-06-25 实测中这把"service key 解不出"误导成"没 placement",排查方向完全跑偏。

## What Changes

- **修改** 前端 `toIngressError` / 错误处理:对非 2xx 响应解析响应体 JSON 的 `detail` 字段并透出真实原因,而非按状态码硬编码文案
- 404 仍可保留"agent not found"友好语义(后端 detail=`agent not found`),但 **503 不再假定 placement**——显示后端 detail(无 detail 时回落到中性"unavailable"提示)
- **同步** `agent-chat-console` spec:把"503 = no node placement"的措辞改为"surface ingress 返回的错误 detail",并更新对应 scenario
- 纯前端改动;后端 ingress 已返回正确 `{detail}`,不改后端

## Capabilities

### New Capabilities

(无)

### Modified Capabilities

- `agent-chat-console`:operator chat 控制台对 ingress 错误的呈现——从"按状态码硬编码文案(503→无 placement)"改为"透出后端 detail",404/503 不再绑死单一原因

## Impact

- `frontend/src/features/chat/api.ts`:`toIngressError` 改为基于响应体 `detail`(需读取 body;函数签名/调用点相应调整)
- `frontend/src/features/chat/api.test.tsx`:更新 404/503 错误映射用例,断言透出 detail(mock body 用 `detail` 键,对齐 FastAPI HTTPException 形状)
- owning surface:frontend SPA(`features/chat`)
- owned tables / config namespace:无
- cross-module dependencies:无;后端契约不变(已返回 `{detail}`)
- migration / shim:无
