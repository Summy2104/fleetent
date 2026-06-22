## 1. agent 入站消费承载 Principal（信任边界内 + 回退）

- [ ] 1.1 **测试（红）**：在 `tests/unit/test_agent_app_tui_auth.py`（或新增 `test_agent_app_principal_carry.py`）覆盖：(a) **传输 token 已验** + 入站带承载 Principal → agent 用**承载的** Principal（其 user_id 进 run_stream，而非 token 自身 principal）；(b) **无承载** Principal → 回退现行 `_validate_tui_token`/`_local_bearer` 自解析（行为不变）；(c) **无有效传输 token + 伪造 Principal 头** → 401/拒，承载头**不生效**（先验 token 后读头）；(d) 承载 `Principal.tenant_id` 与 agent 租户不符 → `_check_tenant` 仍 403。先跑见红。
- [ ] 1.2 **实现（绿）**：`agent_app.py` 入站：在 `_authenticate` 通过（传输鉴权）后读受信头 `X-Fleetent-Principal`（`<user_id>/<tenant_id>` 或紧凑 JSON）；有则用承载 Principal、无则维持自解析；`_check_tenant` 不变、对承载 Principal 同样生效。**确保顺序是「先验 token → 再读头」**（D1）。跑 1.1 见绿。

## 2. forwarder 透传承载 Principal

- [ ] 2.1 **测试（红）**：在 `tests/integration/test_node_forwarder.py` 用例：forwarder 收到带承载 Principal 头的转发请求时，**逐字透传**该头给本机 agent（断言上游 agent 收到的请求头含原样 Principal）。⚠ 沿用 fix-streaming 教训：用真实流式上游、勿内存 mock send。先跑见红。
- [ ] 2.2 **实现（绿）**：`node/forwarder.py` `forward_chat`（及 ws 路径）在构造对 agent 的请求时透传 `X-Fleetent-Principal` 头；不解析、不改写。跑 2.1 见绿。

## 3. 平台 chat-edge 解析 operator → Principal 并承载

- [ ] 3.1 **测试（红）**：在 `tests/integration/test_platform_agent_gateway_ingress.py` 用例：operator（admin session）打 `/admin/agents/{name}/chat`，断言 **agent 侧收到的 Principal = operator 的 user_id**（端到端，经真实 forwarder+agent）。先跑见红（现状 agent 看到的是 token principal）。
- [ ] 3.2 **实现（绿）**：`server.py` `/admin/agents/{name}/chat`：把已认证 operator（admin session → user）解析成 `Principal`；`DirectHttpAgentTransport.chat(...)` 接受并随转发带 `X-Fleetent-Principal` 头。transport/forwarder 仅透传。跑 3.1 见绿。

## 4. `/ws` 同构承载

- [ ] 4.1 **测试（红）**：agent `/ws` + forwarder ws 路径 + 平台 ws ingress：握手阶段带承载 Principal → 整条连接归属该 Principal；无则回退。先跑见红。
- [ ] 4.2 **实现（绿）**：在 ws 握手阶段（传输鉴权后）读承载 Principal 并钉住整连接；forwarder/transport ws 透传该头。跑 4.1 见绿。

## 5. 回归与收尾

- [ ] 5.1 回归：`tests/unit/test_agent_app_tui_auth.py`、`test_platform_agent_gateway.py`、`tests/integration/test_node_forwarder.py`、`test_platform_agent_gateway_ingress.py` 既有用例全绿；直连 TUI / standalone 自解析路径行为零变化（保 `fleetent agent run` 验证基线）。
- [ ] 5.2 `make test-pr` 全绿（对照 main 基线无新增失败）+ 跑相关集成 `uv run pytest tests/integration/test_node_forwarder.py tests/integration/test_platform_agent_gateway_ingress.py -q`（无新增失败）+ 覆盖率门禁 `make test-unit-ci`（--fail-under=76）不被拉破。
- [ ] 5.3 （建议）隔离 dev home live 复跑：经平台 chat console 发消息，确认 agent 侧 trace/会话归属到 **operator 的 user_id**（而非网关 token），作为端到端实证。
