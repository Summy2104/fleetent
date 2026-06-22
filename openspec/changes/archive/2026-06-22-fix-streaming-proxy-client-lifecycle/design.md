## Context

④ 托管 ingress（`platform-agent-gateway`）的流式中继有两处同源 born-broken 写法：

- `src/fleetent/node/forwarder.py`：`forward_chat`（HTTP SSE）、`forward_ws`（WebSocket）
- `src/fleetent/platform/node_management/agent_transport.py`：`DirectHttpAgentTransport.chat`、`.ws`

两处 `chat` 均为：

```python
async with httpx.AsyncClient(timeout=None) as client:
    upstream = await client.send(client.build_request(...), stream=True)
    if upstream.status_code >= 400:
        content = await upstream.aread(); await upstream.aclose()
        return Response(content=...)               # 错误路径：整体读完再返回，OK
    async def _iter():
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await upstream.aclose()
    return StreamingResponse(_iter(), ...)         # 成功路径：return 时 async with 退出 → client 关闭
```

`StreamingResponse` 的 `_iter()` 由 Starlette 在处理函数**返回之后**才迭代。此时 `async with`
已退出、`client` 连接池已关，`upstream.aiter_bytes()` 读到已关连接 → 首块 `httpx.ReadError`、
中继 0 字节。live e2e 实证：直连 agent `127.0.0.1:54727/chat` 完整流式返回，经 forwarder 8786
则 `http_code=200 size=0`。

ws 路径用 `async with websockets.connect(...) as upstream:`，其桥接逻辑全程在 `async with` 体
内（`task_group` 跑完才退出），HTTP chat 那种"返回后才消费"的时序不同；但 transport 侧的
httpx client 若也用 `async with` 包裹则有同类隐患，一并按统一生命周期原则处理。

## Goals / Non-Goals

**Goals:**
- 成功流式路径下，承载 HTTP client 存活到流被完整消费之后；operator 收到 agent 的完整 SSE 流。
- forwarder 与 DirectHttp transport 两侧 `chat` 均修复，时序行为一致。
- 既有契约零变更：node-key 鉴权、TUI token 注入、loopback 路由、`status_code >= 400` 错误整体
  透传、媒体类型透传全部保持。

**Non-Goals:**
- 不改 ingress 路由 / `AgentTransport` 协议 / forwarder 路由签名。
- 不动 dev-stack 配置（`FLEETENT_SECRET_KEY`）、`node_store` 的 `suppress(Exception)`、
  `<node_id>.internal` DNS——这三项 live e2e 同时发现，但机制不同，列入 proposal follow-up 单独处置。
- 不碰 agent 运行时、frontend、schema。

## Decisions

- **D1：client 生命周期与流绑定，不再用 `async with` 包裹返回流。** 在处理函数内创建
  `client = httpx.AsyncClient(timeout=None)`（不进 `async with`），把 `client` 句柄交给 `_iter()`，
  在 `_iter()` 的 `finally` 里**同时** `await upstream.aclose()` 与 `await client.aclose()`。
  错误路径（`status_code >= 400`）在返回 `Response` 前显式关闭 `upstream` 与 `client`（已整体
  读完，立即关无副作用）。这样成功流被完整消费后才关 client，错误路径不泄漏 client。
- **D2：两文件用同一模式修。** forwarder.py 与 agent_transport.py 的 `chat` 都按 D1 改；保证
  时序一致、便于 review。
- **D3：ws 路径按其自身结构保证 client/连接生命周期覆盖整个桥接。** forwarder 的
  `forward_ws` 已在 `async with websockets.connect(...)` 体内跑完 task group 才退出，结构正确，
  仅做必要核对；transport 侧 ws 同理保证连接存活贯穿桥接。不为 ws 强行套用 HTTP 的句柄外提，
  避免过度改动。
- **D4：异常不吞。** `_iter()` 的 `finally` 只做资源关闭；若中继中途异常，按现有 Starlette 流
  语义向上抛，不静默吞（符合「不吞异常」铁律）。

## Risks / Trade-offs

- **手动管理 client 生命周期 → 泄漏风险**：不再有 `async with` 自动关闭，必须确保**每条返回路径**
  （错误 `Response`、成功 `_iter().finally`、`build_request`/`send` 抛异常）都关掉 client。设计上
  在 `send()` 之前不建 client、`send()` 之后任何提前返回都显式 `aclose`，把窗口收到最小。
- **测试时序复现**：bug 的本质是"函数返回后才消费流"。单测必须真正驱动 `StreamingResponse` 的
  body 迭代（消费 `response.body_iterator` / 用 ASGI streaming），断言收到完整多块且非空——
  仅断言 200/headers 会假绿（bug 现场就是 200+0 字节）。这是红/绿能否抓住 bug 的关键。
- **范围克制的代价**：dev-stack 三项 gap 不在本切片，"试用"仍需手动设 `FLEETENT_SECRET_KEY` +
  `/etc/hosts` 映射。已在 proposal 显式记录为 follow-up，避免被当成"已修"。
