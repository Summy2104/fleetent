## Why

`platform-agent-gateway`（④ 托管 ingress）的 SSE 流式中继是 born-broken：operator 经
`POST /admin/agents/{name}/chat` 与 agent 对话时，**收到 200 但响应体为 0 字节**，对话功能完全不可用。

2026-06-22 live e2e 逐跳定位到根因（agent 自身 `/chat` 直连可完整流式返回 `Pong! 🏓`，仅中继层坏）：

```python
# node/forwarder.py  与  platform/node_management/agent_transport.py 同款写法
async with httpx.AsyncClient(timeout=None) as client:   # client 绑定到此 with
    upstream = await client.send(..., stream=True)
    ...
    return StreamingResponse(_iter(), ...)               # return 时 with 退出 → client 关闭
                                                          # 但 _iter() 是 Starlette 之后才迭代
```

`async with httpx.AsyncClient()` 在函数 `return` 那一刻就关闭了 client 及其连接池，而
`StreamingResponse` 的生成器 `_iter()` 是在函数返回**之后**由 Starlette 消费的。等到迭代
`upstream.aiter_bytes()` 时连接已关 → 首次抛 `httpx.ReadError`、随后中继到 0 字节。

这是典型的 streaming-proxy client 生命周期错误：**承载流式响应的 HTTP client 必须存活到流被
完整消费之后**，不能绑死在产生 `StreamingResponse` 的函数作用域里。单测/集成测未覆盖此时序
（多半 mock 了 streaming 或未复现 `async with` 退出时机），故漏到 live e2e 才暴露。

## What Changes

- **node forwarder**（`node/forwarder.py`）：`forward_chat`、`forward_ws` 两处不再用
  `async with httpx.AsyncClient(...)` 包裹返回流；改为让承载 client 的生命周期与被中继的
  流绑定——client 在 `_iter()`（或 ws 中继任务）结束时才关闭，确保流式 body 被完整转发。
- **platform DirectHttp transport**（`platform/node_management/agent_transport.py`）：
  `chat`、`ws` 两处同一 born-broken 写法，同样修正（该侧此前先被单机 dev 的
  `<node_id>.internal` DNS 解析挡住、尚未跑到此 bug，但代码缺陷同源，一并修）。
- 修复后保持既有契约不变：node-key 鉴权、TUI token 注入、loopback 路由、错误状态码透传
  （`status_code >= 400` 时仍 buffer 整体返回）均不变，仅修正成功流式路径的 client 生命周期。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `platform-agent-gateway`: 强化「流式契约」相关要求——承载流式中继的 HTTP client 必须存活到
  流被完整消费，operator 必须收到 agent 的**完整** SSE 流（而非空体/截断）；forwarder 与
  DirectHttp transport 均受此约束。

## Impact

- **owning packages**：`node`（`node/forwarder.py`）、`platform`（`platform/node_management/agent_transport.py`）
- **public API surface**：不变（`AgentTransport` 协议、ingress 路由、forwarder 路由签名均不动）
- **owned tables**：无
- **config namespace**：无
- **cross-module dependencies**：不变；不触碰 agent↔platform 解耦（forwarder 属 node 侧、
  transport 属 platform 侧，依赖方向不变）
- **migration / shim plan**：无 schema、无迁移、无 shim
- 不碰 frontend、不碰 agent 运行时；验证基线（无 platform 时 `fleetent agent run` 直跑）不受影响

### 本次 live e2e 另外发现、不在本切片（建议后续单独立项）

1. **dev-stack 未设 `FLEETENT_SECRET_KEY`**：`make node-provision` 时 `secret_store.set` 抛
   `SecretKeyError`，被 `node_store.register_node` 的 `with suppress(Exception)` 静默吞掉 →
   node service key 不落库 → ingress 503。属 dev 工具链配置，建议在 Makefile dev 目标注入。
2. **`node_store.register_node` 用 `suppress(Exception)` 吞掉安全关键的 secret 持久化**：生产
   隐患（master key 配错时 register "假成功"、key 未落库），违反「不吞异常，必须 log 或
   re-raise」。属健壮性修复，与本流式 bug 机制不同，单独处置。
3. **forwarder URL 写死 `<node_id>.internal:8786`**（生产内网 DNS 契约）：单机 dev 不解析，
   平台侧 `ConnectError`。需 `/etc/hosts` 映射或 dev override，属 dev 网络环境，非代码缺陷。
