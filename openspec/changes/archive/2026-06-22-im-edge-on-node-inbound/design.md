## Context

- IM supervisor 现在在 `agent_app` boot：`_AgentHandle.supervisor: SlackSupervisor` / `telegram_supervisor`（agent_app.py:40-71）。
- `im_gateway/`：adapter（slack.py/telegram.py）+ supervisor（slack_supervisor.py/telegram_supervisor.py）+ normalizer.py（进程内调 `runtime.loop`）+ outbound.py + connector_registry.py（模块级 `(platform,agent_name)→connector`，注释已写"平台进程按 agent_name keys"+"cron 也消费"）+ access.py（`set_im_identity_resolver` 注入口）。
- node→platform API：`node_desired_state_api.py`（`/nodes` 前缀、`_authenticate_node` node-key 鉴权、GET desired-state / POST status）。
- 已落地依赖：#2 `resolve_or_provision`、#3 Principal-carrying 入站（agent /chat 已接受转发 Principal）。
- 护栏：`im_gateway` 既是 agent-runtime（禁 import platform）又是 **edge face**（核禁 import 它）——本切片保前者、强化后者。

## Goals / Non-Goals

**Goals:**
- IM 连接 + 身份解析在 **node**；agent 进程不持 IM 连接（managed）。
- node 经平台端点解析身份（node→platform），im_gateway 仍不 import platform。
- node 转发 `{Principal, IM-event}` 给本机 agent normalizer；**同步回复经 node 发回**。
- standalone（无 platform）下 IM 仍在 agent 进程跑，行为不变。

**Non-Goals:**
- 异步/带外出站（审批 DM、cron 主动外发）→ #4b delivery-queue。
- per-tenant IdP / 域映射（端点吃 tenant 入参，来源不在此）。

## Decisions

- **D1 · node 托管 IM-edge**：node app/reconcile 据 desired-state 为放置的 agent 启 SlackSupervisor/TelegramSupervisor（连接配置从 agent.yaml `im` 块投影）。`agent_app` 在 managed 下**不**启 IM supervisor。
- **D2 · 平台身份端点 + node resolver 注入**：`POST /nodes/{node_id}/identity/resolve`（node-key 鉴权）→ `resolve_or_provision(tenant, verified_email?, channel, platform_user_id)` → `Principal`。node 用 `set_im_identity_resolver` 注入一个**调该端点**的 resolver（im_gateway 不 import platform，沿用既有注入口）。
- **D3 · 转发到 agent normalizer 入站**：node IM-edge 解析出 Principal 后，把 `{Principal, IM-event}` 经 forwarder 转给 agent 的 normalizer 入站（新端点或扩展，跑 `normalizer.route` 带转发 Principal）。复用 #3 的 Principal 信任边界（传输鉴权后信任承载 Principal）。
- **D4 · 同步回复返回式（本切片最实重构）**：normalizer 处理 inbound turn 产生的**同步回复**，managed 下 **从"connector_registry 进程内直发"改为"作为转发响应返回"**，由持连接的 node 发回 IM。standalone 下仍走进程内直发（连接在 agent 进程）。→ 需要在 normalizer 的回复发射点引入"发射目标可注入/可返回"的抽象（managed=返回、standalone=直发）。
- **D5 · standalone 保真**：注入方/部署模式区分——有 node/platform 注入（managed）走 node-edge + 返回式回复；无（standalone）走 agent 进程内 IM + 直发。保 `fleetent agent run` 验证基线。
- **D6 · connector_registry 落 node**：managed 下连接在 node，registry 在 node 侧按 agent 路由（现已按 `(platform,agent_name)` keyed，迁移宿主即可）。cron 出站消费 registry 的部分随 #4b 一起理（本切片只管入站+同步回复）。
- **D7 · 契约/护栏更新**：AGENTS.md 改 im_gateway 执行宿主为 node + 注入方为 node（仍 no-platform-import edge face）；`test_module_dependency_guardrails.py` 对 im_gateway 宿主/edge-face 的描述同步。

## Risks / Trade-offs

- **★同步回复返回式是最大风险**：normalizer.py 与 connector_registry/outbound.py 的出站耦合较深。把"同步回复"从直发改成返回，要精确找到 inbound-turn 的回复发射点、引入注入式 sink（managed 返回 / standalone 直发），且**不碰**异步/cron 出站（那是 #4b）。改错会让回复发不出或 standalone 退化。测试要分别覆盖 managed（回复经 node 返回）与 standalone（进程内直发）。
- **大切片**：跨 node/platform/runtime/im_gateway 四包 + 改 AGENTS.md 契约 + 护栏。收尾必须跑**全量集成**（不只 scoped），尤其任何 IM/normalizer/agent-boot 测试。
- **standalone 退化路径**：必须保证无 platform 时 IM 照跑（resolver=None 退化、连接在 agent、直发）——这是验证基线，回归测试重点。
- **流式/长回复**：IM 同步回复若分块，返回通道要支持（沿用 #3/forwarder 的流式中继；注意 fix-streaming 的 client 生命周期教训）。
- **连接生命周期跨进程**：node 起/停 agent 与开/关其 IM 连接要对齐（owner-task 契约），避免 agent 没了连接还在。
