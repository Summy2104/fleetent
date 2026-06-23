## Why

node 在 reconcile 拉起 managed agent 时，`_write_home` 只 materialize `agent.yaml`，**从不生成 agent home 的 `.env`/`FLEETENT_TUI_TOKEN`**。而 forwarder（`node/forwarder.py`）和 IM-edge（`node/im_edge.py`）都靠读 `<home>/agents/<name>/.env` 里的 `FLEETENT_TUI_TOKEN` 来注入 agent loopback `/chat` 的 Bearer。结果：任何新 pin 到 node 的 agent，经 forwarder ingress（含 admin chat console、IM）对话会直接报 503 `agent '<name>' has no env scaffold`。现有 managed agent（如 demobot）能用，纯属早期手写过 `.env` 的历史巧合——这是一条无法靠产品流程自愈的隐性 gap，新增 agent 即触发。

## What Changes

- node reconcile 在 materialize agent home（写 `agent.yaml`）时，SHALL 同步确保该 home 存在 `.env` 且含一个有效的 `FLEETENT_TUI_TOKEN`（`ma-<64hex>` 形态）；缺失则生成，**已存在的 `.env` 始终保留**（幂等、不覆盖、不轮换已有 token）。
- 该 scaffold 逻辑复用 agent runtime 既有的 `.env` 生成能力（`runtime/agent_init.py`），抽出可复用入口，避免 node 与 `fleetent agent init` 两处各写一份 token 生成逻辑。
- 新 pin 的 managed agent 开箱即可经 forwarder/IM-edge 对话，无需任何手工补 `.env`。

## Capabilities

### New Capabilities
<!-- 无新增 capability -->

### Modified Capabilities
- `node-supervisor`: 幂等 reconcile 的 home materialize 行为新增一条 requirement——materialize SHALL 同时 scaffold agent `.env` 的 `FLEETENT_TUI_TOKEN`（缺失生成、已存在保留），使 forwarder/IM-edge 能稳定取到 agent loopback `/chat` 的 Bearer。

## Impact

- **owning package**: `node/`（`reconcile.py` 的 materialize 步骤新增 `.env` scaffold 调用）
- **public API surface**: `runtime/agent_init.py` 抽出可复用的 `.env` scaffold 入口（如 `ensure_env_scaffold(home_dir, *, referenced_env_names)`），供 node 与 `scaffold_agent_home` 共用；node → runtime 为契约允许的依赖方向（node 拉起/读取 agent runtime）。
- **owned tables**: 无
- **config namespace**: 无
- **cross-module dependencies**: node 依赖 `runtime.agent_init` 的 public 函数；不触碰 platform（node SHALL NOT import platform 不变）。
- **migration / shim plan**: 无 schema/迁移。行为纯增量；已存在 `.env` 保留，旧 home 完全兼容。
- 受影响代码：`src/fleetent/node/reconcile.py`、`src/fleetent/runtime/agent_init.py`；消费侧 `node/forwarder.py`、`node/im_edge.py` 的 `_agent_tui_token` 行为不变（仍读 `.env`），只是其前置条件被 reconcile 自动满足。
- **范围外**：我手工 `pkill` agent 子进程后观察到 node reconcile loop 停摆（疑似与 health-probe bulkhead 要求相关的独立韧性问题），不在本 change 范围，必要时另开。
