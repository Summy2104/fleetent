# e2e-managed-stack-coverage Specification

## Purpose
为 managed 拓扑补齐可复用多进程 e2e harness 与首批 P0 端到端覆盖，验证 platform、node、agent 真进程整合路径。
## Requirements
### Requirement: 可复用多进程 managed 栈 e2e harness

项目 SHALL 提供一个可复用的 e2e harness，在测试内起**真实多进程 managed 栈**——platform 进程 + node 进程 + 每 agent 进程，经真实 forwarder/HTTP 通信——并在 teardown 干净停止。harness SHALL：隔离临时 home + 临时迁移好的管理库（不触碰 `data/`）、动态分配端口、注入 dev master key（`FLEETENT_SECRET_KEY`）、走 node-provision 落 service key。harness SHALL 含一个**确定性 LLM stub**（本地 OpenAI 兼容 SSE、无云依赖），agent 经其 model `base_url` 指向 stub，使断言固定、不调真 LLM。

#### Scenario: harness 起整栈并可达

- **WHEN** e2e 用 harness 起栈
- **THEN** platform/node/agent 三进程起来、互联（node 注册、agent 被 spawn），测试可经 platform 入口驱动；测试结束 harness 干净停所有进程、不留孤儿

### Requirement: managed chat ingress 端到端 e2e

SHALL 有一条 e2e 经真实多进程栈验证 operator 对话全链路：admin 登录 → `POST /admin/agents/{name}/chat` → platform → node forwarder → agent loop → 确定性 LLM stub → **流式回复**回到 operator。

#### Scenario: operator 经 managed 栈拿到流式回复

- **WHEN** admin 登录后经 ingress 发消息给一个放置于 node 的 agent
- **THEN** 收到非空的端到端流式回复（经 platform→node→agent→stub），证明三进程整合 + 流式中继 + 身份/服务 key 鉴权链通

### Requirement: node 生命周期 e2e

SHALL 有一条 e2e 验证 node 真 subprocess 生命周期：注册 → 拉 platform desired-state → spawn agent 子进程 → agent `/health` 健康。

#### Scenario: node 拉起 agent 并健康

- **WHEN** node 起后拉到含某 agent 的 desired-state
- **THEN** node spawn 该 agent 子进程，agent loopback `/health` 返回健康，node 据此上报

### Requirement: e2e 跑独立 slow lane，不进 per-merge 门禁

多进程 e2e SHALL 在独立的 slow/nightly lane 运行（如 `make test-e2e`），**不**纳入 per-merge `make test-pr` 门禁（e2e 慢、需起多进程）。

#### Scenario: per-merge 门禁不含多进程 e2e

- **WHEN** 跑 per-merge 门禁
- **THEN** 不运行多进程 e2e（它们在独立 lane）；e2e 失败在其专属 lane 暴露
