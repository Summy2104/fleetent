## Why

IM 入站对话、高危工具的审批 DM 往返、以及 directed-reach 的 `notify_user` fan-out 投递，是 managed 部署面向真实用户的三条核心链路。它们至今**只有单进程 unit/integration 覆盖**——没有一条 e2e 在真实多进程 managed 栈下证明「IM 消息进来 → loop 跑 → 回复出去」「高危工具挂起 → 审批 DM 入队 → 用户 `approve <id>` → run 恢复」「`notify_user` 入队 directed 目标 → node drain 反查用户地址 → 尝试 fan-out」。这三条都是回归代价极高的用户可见路径，必须有端到端守门。地基 harness（`e2e-managed-stack-coverage` 已落地，`managed_stack` fixture + `_llm_stub`）正好解锁这批覆盖。

## What Changes

- 新增 e2e（纯 `tests/e2e`，零 src 改动），在真实多进程 managed 栈下覆盖：
  - **IM 入站同步回复**：经 agent `POST /im/route`（携 `X-Fleetent-Principal`）→ `normalizer.route` → loop → `ImRouteResponse.replies` 同步回复（确定性 LLM stub）。
  - **审批 DM 往返**：触发高危工具 → `permission_gate.request_approval` → `_notify_approvers` 入队 `im_outbound_queue` → 用户经 `/im/route` 发 `approve <id>` → `normalizer` 命中审批命令 → `approval_router.resolve_approval_request` → 挂起的 run 恢复。
  - **`notify_user` fan-out 投递原语**：直接往 agent 侧 `im_outbound_queue` 注一条 directed 目标行（`platform=directed`、`address_json={"target_type":"user_id","user_id":...}`），验证 node drain 反查 `POST /nodes/{id}/identity/addresses` 并尝试 fan-out——断言「入队形状正确 + node 发生地址反查（平台侧可观测）」，**不**断言真投递（无真 Slack/Telegram connector）。
- 新增 e2e 专属 helper `tests/e2e/_im_helpers.py`（本 change 独占文件，**不重构**核心 `managed_stack` fixture）。
- 进 slow/nightly lane（`make test-e2e`），**不**进 per-merge `make test-pr`。

## Capabilities

### New Capabilities
- `e2e-im-inbound-approval`: 多进程 managed 栈下的 IM 入站 / 审批 DM 往返 / `notify_user` fan-out 投递原语端到端覆盖。

### Modified Capabilities
（无；不改任何现有 capability 的 requirement，纯新增 e2e 覆盖。）

## Impact

纯测试侧改动，零 src 产品代码改动。

- **owning package**：`tests/e2e`（新增 test 文件 + `_im_helpers.py`）；复用 `tests/e2e/conftest.py::managed_stack` 与 `tests/e2e/_llm_stub.py` 既有基建
- **public API surface**：无（纯测试侧；不新增/改 src public API）
- **owned tables**：无（只读/注入验证 agent 侧既有 `im_outbound_queue`；不新增表）
- **config namespace**：无
- **cross-module dependencies**：测试编排既有 platform/node/agent 三进程链路（`/im/route`、`permission_gate`、`approval_router`、`outbound_connectors`、node `_deliver_user_id_intent`、`/nodes/{id}/identity/addresses`）；不引入 src 跨模块依赖
- **migration / shim**：无
- **受影响代码**：仅 `tests/e2e/`；核心 `managed_stack` fixture 与 `conftest.py` 核心**冻结不动**，新 helper 落独占 `tests/e2e/_im_helpers.py`，避免与并行 e2e 波（D2/D3/D5）撞 `conftest.py`
- **CI**：进 `make test-e2e` slow/nightly lane，不进 per-merge 门禁
- **边界划分（与 D5 不抢地盘）**：本 change 只测 `notify_user` fan-out 的**投递原语**（直接注队列行 → node 反查 → 可观测点）；**reflection 提案 → 审批 → apply 的 directed-reach（A4b）全程归 D5（`e2e-reflection-lifecycle`），本 change 不碰 reflection**
