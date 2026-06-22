## 1. 平台身份解析端点（node→platform）

- [x] 1.1 **测试（红）**：`tests/integration/test_node_desired_state_api.py`（或新文件）：`POST /nodes/{node_id}/identity/resolve` 带 **node service key** + 渠道身份（platform/platform_user_id/可选 email/tenant）→ 返回 `Principal`（经 `resolve_or_provision`，与进程内解析同结果）；**无/错 node key → 401/403**。先跑见红。
- [x] 1.2 **实现（绿）**：在 `node_desired_state_api`（`/nodes` 前缀、`_authenticate_node`）加该端点，调 #2 的 `resolve_or_provision`。跑见绿。

## 2. node 侧 resolver（调端点）+ node 托管 IM-edge

- [x] 2.1 **测试（红）**：node 注入的 IM 身份 resolver 调上面的端点解析（respx/stub 平台端点）→ 得 user_id；`im_gateway` 不 import platform（护栏不破）。node 据 desired-state 为放置 agent 启 SlackSupervisor/TelegramSupervisor（连接配置投影自 agent.yaml `im`）。先跑见红。
- [x] 2.2 **实现（绿）**：node app/reconcile 启 IM-edge supervisor（为放置 agent）；`set_im_identity_resolver` 注入"调端点"的 resolver；connector_registry 宿主迁 node 按 agent 路由。跑见绿。

## 3. agent normalizer 入站（接转发的 Principal+IM-event）

- [x] 3.1 **测试（红）**：agent 暴露的 normalizer 入站，收到 forwarder 转发的 `{Principal, IM-event}`（传输鉴权后信任承载 Principal，复用 #3）→ 跑 `normalizer.route`、按该 Principal 归属；跨租户仍 `_check_tenant` 拒。先跑见红。
- [x] 3.2 **实现（绿）**：agent_app 加/扩 normalizer 入站端点（用转发 Principal + IM payload 调 normalizer.route）。跑见绿。

## 4. ★同步回复返回式（managed 经 node 发回 / standalone 进程内直发）

- [x] 4.1 **测试（红）**：(a) **managed**：normalizer 处理 inbound turn 的**同步回复**作为转发响应**返回**、不经进程内 connector 直发，node 收到后发回 IM；(b) **standalone**：无平台注入时，同步回复仍走进程内 connector 直发（行为不变）。先跑见红。
- [x] 4.2 **实现（绿）**：在 normalizer 的同步回复发射点引入**可注入 sink**（managed=返回给转发响应；standalone=进程内直发）；**不碰**异步/cron 出站（#4b）。跑见绿。

## 5. agent_app 停启 IM（managed）+ standalone 保真

- [x] 5.1 **测试（红）**：managed（有 node/平台注入）下 `agent_app` **不**启 IM supervisor；standalone（无注入）下仍启、IM 在 agent 进程跑、`fleetent agent run` 对话+IM 正常。先跑见红。
- [x] 5.2 **实现（绿）**：agent_app boot 按模式区分启不启 IM supervisor。跑见绿。

## 6. 契约 + 护栏 + 收尾

- [x] 6.1 更新 `AGENTS.md`：im_gateway 执行宿主=node、注入方=node（仍 no-platform-import edge face）；`test_module_dependency_guardrails.py` 对 im_gateway 宿主/edge-face 的描述同步（im_gateway 仍禁 import platform 不变）。**非代码产物（AGENTS.md）须人工确认再 commit。**
- [x] 6.2 边界核验：`PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` + 依赖护栏测试全绿（im_gateway 仍不 import platform；核不 import edge face；无新增 agent→platform）。
- [x] 6.3 **跨切面收尾**：本 change 跨 node/platform/runtime/im_gateway + 改 AGENTS.md + 护栏 → 跑**全量集成** `uv run pytest tests/integration -q`（不只 scoped；判"无新增失败"），重点 IM/normalizer/agent-boot/forwarder 类；`make test-pr` 全绿；覆盖率门禁 `make test-unit-ci`（--fail-under=76）不被拉破。
- [ ] 6.4 （建议）live 实证：managed 栈下经真实/stub IM 入站 → 确认 agent 侧会话归属真实 user（经平台解析）+ 同步回复发回；standalone `fleetent agent run` IM 仍跑。
