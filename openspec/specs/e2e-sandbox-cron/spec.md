## Purpose

本 spec 规定沙箱 run_code 与 cron 定时任务在真实多进程 managed 栈下的端到端测试覆盖，以及 e2e 测试的 slow lane 运行策略。

## Requirements

### Requirement: 沙箱 run_code 在 agent loop 中端到端执行 e2e

SHALL 有一条 e2e 验证：在真实多进程 managed 栈下，agent 经对话触发 `run_code` 工具 → 沙箱后端执行代码 → 执行输出端到端回折到 chat 回复。该 e2e SHALL 复用既有 `managed_stack` + 确定性 LLM stub，stub 须能产出一条调用 `run_code` 的 assistant 决策。

#### Scenario: agent 触发沙箱并把执行输出返回 chat

- **WHEN** 沙箱后端可用（`available()` 为真），且向 managed 栈下的 agent 发一条会触发 `run_code` 的指令
- **THEN** 沙箱执行该代码，且其标准输出经 agent loop 折回，出现在 chat 的最终回复中

#### Scenario: Docker / 沙箱后端不可用时优雅 skip

- **WHEN** 沙箱后端 `available()` 为假（如 e2e 环境无 Docker CLI / Docker daemon 不可达）
- **THEN** 本沙箱 e2e 通过 `pytest.skip` 跳过而非失败（沙箱是 optional feature，降级 OFF 不应让测试硬挂）

### Requirement: cron 任务创建并触发 agent e2e

SHALL 有一条 e2e 验证：在真实多进程 managed 栈下，创建一个 scheduled task 并使其触发 → agent 跑通该任务的消息 → agent 的执行结果可观测（cron run-state 写回，或投递的回复）。创建/触发/观测的接缝 SHALL 由本 change 独占的 `tests/e2e/_cron_helpers.py` 封装，**不重构** `managed_stack`。

#### Scenario: 任务创建后触发，agent 跑通且结果可观测

- **WHEN** 在 managed 栈下创建一个 scheduled task，并使其触发（手动 `run_now` 或等到下次 fire）
- **THEN** agent 经 `_fire()` → `_agent_run()` 跑通该任务，且其执行结果可被观测到（如 `schedule_store` 的 last_run_at/last_status run-state 写回，或投递出的回复内容）

### Requirement: e2e 跑独立 slow lane，不进 per-merge 门禁

本 change 的多进程 e2e SHALL 在独立 slow lane 运行（`make test-e2e` / `pytest tests/e2e`），**不**纳入 per-merge `make test-pr` 门禁。

#### Scenario: per-merge 门禁不含本 e2e

- **WHEN** 跑 per-merge 门禁（`make test-pr`）
- **THEN** 不运行本 change 的沙箱 / cron e2e（它们只在 `make test-e2e` slow lane 内）
