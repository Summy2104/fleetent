## Why

IM（Slack/Telegram）多轮异步场景：用户在 agent 长跑工具循环时想补一句、换方向或打断，但现状 `normalizer.route()` 在整个 run 期间持有 `session_lock`——第二条消息只能阻塞成"下一个 turn"（无反馈、无法影响进行中的任务），或取消重来。缺少"运行中转向（steering）"。

## What Changes

- **新增 `runtime/steering.py`**：per-session 活跃 run 登记表 + pending 邮箱（`asyncio.Queue`，带上限）；API `register_run`（asynccontextmanager）/ `steer` / `interrupt` / `is_running` / `drain`。module-level、测试可 `reset()` 注入。
- **`runtime/loop.py`**：`run()` 与 `run_stream()` 主循环在**压缩之后、sanitize 之前** `_drain_steering(session_id, messages)`——被动消费（登记由输入源做；无 session / 无 handle 时 no-op），把运行中注入的用户消息追加进序列。
- **`im_gateway/normalizer.py`**：`route()` 在抢 `session_lock` **之前** `is_running` 分派——`steer`（默认，注入进行中任务）/ `interrupt`（取消当前 run）/ `queue`（维持串行，加"排队中"提示）；启动 run 时用 `register_run` 包裹并传 `cancel_token`。
- **配置**：`AgentFile` + `GovernanceConfig` + `_governance_from_file` 加 `steering_mode`（默认 `"steer"`，用户拍板）/ `steering_max_pending`（默认 8）。

## Capabilities

### New Capabilities

- `agent-input-steering`: 运行中把新用户输入注入/打断进行中的 agent run，按每-agent steering_mode 分派。

### Modified Capabilities

（无）

## Impact

- **修改文件**：`src/fleetent/runtime/loop.py`、`src/fleetent/im_gateway/normalizer.py`、`src/fleetent/agent_config.py`、`src/fleetent/runtime/snapshot.py`；**新增** `src/fleetent/runtime/steering.py`。
- **默认行为变化**：IM 运行中追加的消息默认 `steer`（注入当前任务），而非隐式串行成新 turn——经用户确认。
- **解耦合规**：纯 agent 侧、asyncio、无 platform、无 DB；steering 登记表是 module-level 可注入可 reset 状态（符合"全局可变状态须可 monkeypatch 注入"）。
- **暂缓（documented，后续小项）**：TUI `METHOD_STEER`、`run_stream` 流式落库（TUI steer 持久化）、collect 合并/去抖。IM 路径经 `run()` 天然落库，是主场景。
