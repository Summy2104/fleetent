# fix-cron-store-and-once

## Why

定时任务在生产暴露了用户可见故障（Jira AAA-8288「发送间隔被 10s 轮询拉长」、AAA-8279 的「间隔不正确 / 不发送」），经可执行脚本复现实证为三个实现缺陷：① `schedule_store.update_run_state` 是整行覆盖（PUT 非 PATCH），每次 fire 后把 `next_run_at` 清空，导致 interval 任务每周期累积漂移（≈运行时长+tick）、`last_status/last_error` 存活不足一个 tick；② once 任务失败后停在过去的 `next_run_at` 上被每 ~2 个 tick 无退避重跑（每次烧一次完整 LLM run，永不停止）；③ once 的 `run_at` 完全忽略任务 timezone，naive 输入按服务器系统时区解释——UTC 容器上中国用户的绝对时间任务晚 8 小时触发。三者均有测试盲区掩护（poll-engine 测试 stub 掉 `_fire`，fire 测试把 `update_run_state` patch 成 no-op），须一并补上贯通测试。

## What Changes

- `schedule_store.update_run_state` 改为**字段选择性更新**：只 UPDATE 调用方显式传入的列（sentinel 区分「未传」与「置 NULL」），写状态列不再抹掉 `next_run_at`，反之亦然
- interval 恢复**固定网格（fixed-rate）语义**：fire 后 `next_run_at` 保持 claim 时推进的网格值（`前一计划时刻 + interval`，过期则整周期快进），不再被清空后重锚到 tick 时刻
- **BREAKING**：once 任务 fire 失败改为**终结**——`enabled=0` + `last_status="error"`（原行为=每 ~2 tick 无限热重试；用户可 `run_now` 手动重试）。成功路径仍标记 `completed`，不变
- fire 失败（agent error 或 delivery error）时，调度器 **best-effort 向任务的可解析投递目标发送失败告警**（⚠️ 文案），告警失败只记日志，绝不影响 fire 结果
- generate 任务 fire 时投递目标解析为空（origin 缺失且无显式 deliver，且非 `deliver.mode="none"`）→ 记 `error`（`no_delivery_target`）而非现在的 `ok`
- `_parse_run_at` 接收任务 timezone：naive ISO 输入按**任务时区**（显式 > 部署默认 > UTC）解释为 aware 时间，落库永远带 offset；相对时长（`+30m`）与带 offset 输入行为不变
- 新增**贯通集成测试**：真实 store + 真实 `_fire`、仅 stub `_agent_run`，覆盖「fire → 写回 → 下个 tick」接缝（现有测试盲区）
- 同步更新 `docs/capabilities/scheduling.md` 的 once 失败策略与 run_at 时区语义描述

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `cron-scheduled-tasks`: ①运行状态写回改为字段选择性（PATCH）语义，写回不得清除 `next_run_at`；②interval 下一次触发锚定前一**计划**时刻（网格），非运行完成时刻；③once 失败终结策略（不自动重试）取代「restart 前可重试」的旧表述；④naive `run_at` 按任务时区解释并以 aware 形式持久化
- `scheduled-task-delivery`: ①新增 fire 失败主动告警要求（best-effort、不影响 fire 结果）；②generate fire 无可解析目标且非显式 `mode="none"` 时记 `error` 而非 `ok`

## Impact

- **代码**：`src/fleetent/schedule_store.py`（`update_run_state`）、`src/fleetent/cron_scheduler.py`（`_parse_run_at`/`compute_next_run` once 分支、`_complete_once`、`_fire`/`_deliver` 告警路径、facade `create_task` 归一化）
- **测试**：`tests/integration/test_cron_poll_engine.py` 等新增贯通用例；`tests/unit/test_cron_parse_run_at.py`、`tests/integration/test_cron_timezone_resolution.py` 补 once 时区用例；复现脚本三个疑点转正为回归测试
- **数据**：无 schema 变更、无嵌入式迁移、无 Alembic；`scheduled_tasks`/`scheduled_task_runs` 既有列与状态词汇表复用
- **模块边界**：全部改动在 agent 侧（`cron_scheduler.py`、`schedule_store.py`），不触碰 `fleetent.platform.*`，不新增跨包依赖
- **行为兼容**：唯一破坏性变化是 once 失败不再自动重试（详见 design「once 失败策略」）；`docs/capabilities/scheduling.md` 需同步
- **关联 Jira**：AAA-8288（关单判据：60s interval 连续 10 次 fire 间隔 ∈ [60,70)s 无累积漂移）、AAA-8279 之「间隔不正确/不发送」
