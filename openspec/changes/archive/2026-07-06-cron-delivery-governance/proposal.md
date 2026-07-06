# cron-delivery-governance

## Why

Jira AAA-8279「定时任务发送错频道」的直接来源是投递目标配置缺乏治理：`notify_platform`/`notify_target` 只填一个时被**静默忽略**、回落到创建频道（用户以为配了目标，实际发回原频道）；generate 任务创建时不校验目标可解析性（无 origin 且无显式 deliver 的任务照建，fire 时产出无处可去）；创建回执不显示最终投递目标，错配要等到点后才暴露。另有一个防御缺口：定时触发的 agent run（fired run）工具集中仍含 `schedule` 工具，action 型任务运行中可再创建定时任务——被 prompt 注入或模型误操作时形成自我增殖循环（参考 hermes cron 对 `cronjob` toolset 的强制禁用）。

按 2026-07-06 决策，本 change **不引入任何审批门**——与既有 spec「`schedule` SHALL NOT require human approval」保持一致；治理手段限于创建期校验与回执透明。

## What Changes

- `notify_platform` 与 `notify_target` **只提供一个**时，create 返回明确 error（不再静默忽略回落 origin）
- create 成功回执**明示最终投递目标**（显式 `platform:target(type)` 或「创建会话 origin」），**无可解析目标时回执显式警示**（不阻断创建——fire 期已由 change-1 的 `no_delivery_target` 兜底为失败并告警，创建期只做可见性提示，不做硬拒绝）
- fired run（generate 与 action）的工具集中**移除 `schedule` 工具**：定时触发的运行不能创建/修改定时任务（防自我增殖）
- `schedule` 工具 schema 的参数描述同步上述契约

**实现期调整（已放弃的方案）**：原计划对无目标的 `generate` 任务做**创建时硬拒绝**（镜像 notify 校验）。实现中发现：①该场景在 fire 时已被 change-1 的 `no_delivery_target` + 失败告警完整覆盖，硬拒绝只是把同一个信号提前到创建时，边际收益是「fail-fast」而非「补一个洞」；②硬拒绝在工具层或 store 层都会牵连大量既有测试（`schedule_store.create` 是测试基础设施广泛复用的构造原语，`test_tools_schedule.py` 内本身也有 7+ 个无关测试依赖「无目标仍可创建」）。改为在创建回执中做**警示型透明化**——收益相近（用户创建当下就能看到「⚠️ 无可解析投递目标」），零测试破坏面，也不引入「测试基础设施因产品语义校验被迫大改」的耦合。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `cron-scheduled-tasks`: ①`schedule` 工具契约新增 half-set 参数拒绝与回执明示/警示投递目标；②fired run 的工具 schema 排除 `schedule`（generate/action 均适用）

## Impact

- **代码**：`src/fleetent/tools/builtin_tools.py`（`schedule` 工具参数校验与回执）、`src/fleetent/cron_scheduler.py`（`_agent_run` 传工具排除）、`src/fleetent/runtime/loop.py`（工具排除机制复用/扩展 `suppress_outbound_tools` 既有通路）
- **测试**：`tests/integration/test_tools_schedule.py`、`test_typed_scheduled_tasks.py`、`test_cron_typed_dispatch.py` 等新增用例
- **数据**：无 schema 变更
- **模块边界**：全部 agent 侧；不触碰 platform；无新增跨包依赖
- **行为兼容**：half-set 从「静默接受」变为「拒绝创建」——只影响新建任务；无目标 generate 仍可创建（回执警示，fire 期由 change-1 兜底为失败+告警）；fired run 失去 schedule 工具是收紧，「任务自我管理」场景改由用户交互式操作
- **关联 Jira**：AAA-8279 之「发送错频道」
