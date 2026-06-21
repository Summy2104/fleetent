## 1. node forwarder 流式中继 client 生命周期

- [ ] 1.1 **测试（红）**：在 `tests/integration/test_node_forwarder.py` 新增一个用例，
  起一个**真实流式上游 agent**（真 socket，如 loopback 上的 uvicorn / 真 ASGI server），其
  `/chat` 分多块 emit SSE；经 forwarder（node-key 鉴权）请求并**完整消费** forwarder 返回流的
  body，断言收到全部块、body 非空。
  ⚠️ **不得 monkeypatch `httpx.AsyncClient.send` 返回内存 Response**——那样 client 关不关都
  不影响 `aiter_bytes()`，bug 会假绿（现有 `test_forwarder_chat_requires_node_key...` 正是如此）。
  必须真实连接，才能让"client 提前关闭"切断字节流。先在当前代码跑：**必须见红**（200 + 0 字节 /
  `ReadError`）。
- [ ] 1.2 **实现（绿）**：改 `src/fleetent/node/forwarder.py` 的 `forward_chat`：不再用
  `async with httpx.AsyncClient(...)` 包裹返回流；改为函数内建 `client = httpx.AsyncClient(timeout=None)`，
  把 `client` 句柄交给 `_iter()`，在 `_iter()` 的 `finally` 里同时 `await upstream.aclose()` 与
  `await client.aclose()`；错误路径（`status_code >= 400`）返回 `Response` 前显式关闭 `upstream`
  与 `client`；`send()` 抛异常路径也确保 `client` 被关。跑 1.1 用例：**必须见绿**。
- [ ] 1.3 核对 `forward_ws`：确认其 `async with websockets.connect(...)` 体内跑完 task group 才
  退出、连接生命周期已覆盖整个桥接，无同类提前关闭；如有则按同原则修，并补 ws 完整桥接断言。

## 2. platform DirectHttp transport 流式中继 client 生命周期

- [ ] 2.1 **测试（红）**：在 `tests/integration/test_platform_agent_gateway_ingress.py` 新增用例，
  以**真实流式上游**（真 forwarder/agent，真 socket）驱动 `DirectHttpAgentTransport.chat`，
  完整消费返回流，断言完整非空。同样**禁止内存 mock `send`**。当前代码：**必须见红**。
- [ ] 2.2 **实现（绿）**：按 1.2 同一模式改
  `src/fleetent/platform/node_management/agent_transport.py` 的 `chat`（client 句柄外提、
  `_iter().finally` 关 upstream+client、错误/异常路径显式关）。跑 2.1：**必须见绿**。
- [ ] 2.3 核对 `DirectHttpAgentTransport.ws`：确认 websocket 桥接的连接生命周期贯穿 task group，
  无提前关闭；必要时同原则修。

## 3. 回归与收尾

- [ ] 3.1 跑 `tests/unit/test_platform_agent_gateway.py` 与 `tests/unit/node/test_app.py`，
  确认既有契约用例（鉴权、token 注入、loopback 路由、错误状态码透传、媒体类型透传）仍绿；
  如现有 mock 式流断言需适配新生命周期则更新（保持其原意，不削弱）。
- [ ] 3.2 `make test-pr` 全绿（对照 main 基线无新增失败）+ 跑本 change 相关集成测试
  `uv run pytest tests/integration/test_node_forwarder.py tests/integration/test_platform_agent_gateway_ingress.py -q`，无新增失败。
- [ ] 3.3 （可选但建议）在隔离 dev home 手动复跑 live e2e：设 `FLEETENT_SECRET_KEY` + provision
  node + 经 forwarder `POST /forward/agents/<agent>/chat` 拿到**完整** `Pong` 流，作为修复实证。
