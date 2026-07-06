# cron-hardening

## Why

定时任务专项评审（2026-07-06）除已实证的功能缺陷（change-1/2 处理）外，还发现一组可用性/健壮性弱点，参照 vixie-cron（timeDiff 分级补跑）与 hermes-agent（inactivity 看门狗、绝不静默禁用）的成熟实践收敛：①宕机多日后重启会无条件补跑一次陈旧的 cron 定点任务（三天前的 daily digest 突然发出）；②`_tick` 遍历无 per-row 容错，一行损坏的 origin/deliver JSON 会让每个 tick 都失败、调度器整体永久瘫痪（boot 的舱壁只护 `_register`）；③boot 遇坏行静默禁用，用户只能从 list 里偶然发现任务变 paused；④fire 无超时保护——一次卡死的运行永久占住 `_inflight` 与 1/4 并发槽，4 个卡死即调度器全瘫；⑤固定 session 绑定特性已实现但 `schedule` 工具未暴露，「计数器」类跨触发记忆场景用户不可达（AAA-8209 根因）；⑥tick 固定 10s 步长使触发时刻带 ≤10s 抖动；⑦死代码（`_parse_cron` 仅测试引用、store `anchor` 列只写不读）。

## What Changes

- **misfire 宽限分级**（F5）：cron 型定点任务迟到超过 `min(半周期, 2h)` 时跳过本次并记 `missed` run-history 行（fast-forward 到下一未来时刻），宽限内仍补跑一次；interval/once 行为不变
- **tick per-row 容错**（F6.1）：单行解码/注册/判定异常只跳过该行并记日志，tick 与其余任务不受影响
- **禁用必告警**（F6.2）：boot/注册期因坏数据禁用任务时，best-effort 向任务 origin 投递一条禁用告警（复用 change-1 的失败告警通路）
- **fire 看门狗**（F6.3）：每次 fire 包超时（新配置 `scheduling.fire_timeout_seconds`，默认 900，0=关闭），超时取消运行、记 `error`（timeout）、释放 in-flight 与并发槽
- **暴露 session 绑定**（F6.4）：`schedule` 工具 create 增加可选 `session` 参数透传 `session_id`（既有 fixed-session 语义不变，仅补工具入口）
- **tick 消抖**（F7）：tick 睡眠改为 `min(tick_interval, 距最早 next_run_at 的时间)`（下界 0.5s），触发抖动从 ≤tick_interval 收敛到亚秒级
- **死代码清理**（F6.5）：删除 `_parse_cron` 及其孤儿测试；`anchor` 列保留 schema（不做迁移）、店面注明 vestigial

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `cron-scheduled-tasks`: ①Missed-run handling 增加 cron 型宽限上界与 `missed` 记录；②poll engine 增加 per-row 容错与到期对齐睡眠；③boot 禁用坏行时告警（不再纯静默）；④Bounded parallel execution 增加 per-fire 超时；⑤Scheduler global settings 增加 `fire_timeout_seconds`
- `scheduled-task-session-binding`: 新增「session 绑定经 schedule 工具可配置」要求（工具入口，语义不变）

## Impact

- **代码**：`src/fleetent/cron_scheduler.py`（`_tick`/`_dispatch`/`_run_tick_loop`/`compute_next_run` 宽限判定）、`src/fleetent/config.py`（`SchedulingSettings.fire_timeout_seconds`）、`src/fleetent/tools/builtin_tools.py`（`session` 参数）、`src/fleetent/schedule_store.py`（`_decode` 容错）
- **测试**：poll engine/typed dispatch/tools schedule 各层新增用例
- **数据**：无 schema 变更（`missed` 已在 run-history 状态词汇表内；`anchor` 列保留）
- **Config namespace**：`scheduling.fire_timeout_seconds`（新增，默认 900）
- **模块边界**：全部 agent 侧；F6.2 复用 change-1 告警助手——**本 change 依赖 change-1 先合并**
- **行为兼容**：宕机多日的 cron 定点任务从「补跑一次」变为「记 missed 跳过」——写入 release note；其余为纯加固
