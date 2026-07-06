# Tasks — fix-cron-store-and-once

> 每个实现 task 严格 TDD：先写测试见红（`uv run pytest <file>::<test> -x -q`）→ 实现见绿。测试任务一律在对应实现任务之前。

## 1. store 字段选择性写回（F1，修 AAA-8288）

- [x] 1.1 写 store 层测试：`update_run_state` 只更新显式传入的列——写 `last_run_at/last_status` 不改 `next_run_at`；写 `next_run_at` 不改状态列（`tests/integration/test_schedule_store.py` 新用例）→ 见红
- [x] 1.2 写贯通集成测试：真实 store + 真实 `_fire`（仅 stub `_agent_run` 返回 `[SILENT]`），断言 fire 后 `next_run_at` == claim 时推进的网格值（非 NULL）、`last_status` 在后续 tick 仍存活、60s interval 连续多次 fire 无累积漂移（`tests/integration/test_cron_poll_engine.py` 新用例）→ 见红
- [x] 1.3 实现：`schedule_store.update_run_state` 改为 `_UNSET` sentinel + 动态 SET 子句（design D1）→ 1.1、1.2 见绿
- [x] 1.4 跑受影响层：`tests/integration/test_schedule_store.py`、`test_cron_poll_engine.py`、`test_cron_scheduler.py` 无新增失败

## 2. once 失败终结（F2a）

- [x] 2.1 写测试：once fire 失败（stub `_agent_run` 抛错）→ 行变为 `enabled=0`、`last_status="error"`、`last_error` 保留；后续多个 tick 不再产生新 fire（复现脚本疑点 3 的反转）→ 见红
- [x] 2.2 实现：once 收尾从「仅 ok 终结」扩展为「ok → completed；error → error 终结」（design D2）→ 见绿
- [x] 2.3 确认成功路径回归：既有 `Once task marked completed after firing` 相关用例仍绿

## 3. 失败主动告警（F2b）

- [x] 3.1 写测试：①agent run 失败且 origin 可解析 → 假 connector 收到含任务名的 ⚠️ 告警，run 仍记 error；②告警投递失败只记日志、不改 fire 结果；③recurring 连续失败仅 streak 首次告警（前次 last_status 已 error 则不发）→ 见红
- [x] 3.2 实现：`_fire` 失败路径 best-effort 告警（复用 `_deliver` 冻结文案，streak 判定读写回前的旧 `last_status`，design D3）→ 见绿

## 4. 无目标 generate 记 error（F2c）

- [x] 4.1 写测试：无 origin、无 deliver 的 generate fire 产出非静默回复 → `last_status="error"`（no_delivery_target）且 history 同步；`deliver.mode="none"` → 仍 `ok`；`[SILENT]` 回复 → 仍 `ok` → 见红
- [x] 4.2 实现：`_fire`/`_deliver` 目标解析为空时按 delta spec 语义记 error（区分 mode="none"）→ 见绿
- [x] 4.3（追加）修复两个因 F2c 收紧而失真的既有用例：`test_once_task_marked_completed_after_fire`（补 `[SILENT]` 隔离测试意图）、`test_complete_once_only_marks_successful_tasks`（重命名+更新为 F2a 新契约：失败 once 也终结，仅不写 completed）

## 5. run_at 任务时区（F3）

- [x] 5.1 写单测：`_parse_run_at("2026-07-08 09:00", tz="Asia/Shanghai")` → aware `+08:00`；相对时长与带 offset 输入行为不变（`tests/unit/test_cron_parse_run_at.py` 扩展）→ 见红
- [x] 5.2 写集成测试：naive run_at + Asia/Shanghai、宿主 TZ=UTC，经工具 create → 持久化 `run_at`/`next_run_at` 带 `+08:00` 偏移、等价 01:00 UTC（`tests/integration/test_cron_timezone_resolution.py` 补 once 用例）→ 见红
- [x] 5.3 实现：`_parse_run_at` 增加 `tz` 参数；facade `create_task` 归一化与 `compute_next_run` once 分支传任务时区（优先级 显式 > 部署默认 > UTC，design D4）→ 见绿
- [x] 5.4 确认存储不变式：全链路无 naive 时间落库（断言持久化值含 offset）

## 6. 文档与收尾

- [x] 6.1 更新 `docs/capabilities/scheduling.md`：once 失败终结策略、失败告警、run_at 时区语义三节
- [x] 6.2 change 收尾：`make test-pr`（`tests/unit -n auto` 4299 passed + 层边界检查 + 改动文件 ruff format/check 全绿）+ `make test-integration-ci`（2284 passed, 1 skipped）无新增失败——两者各命中同一个与本改动无关的预置基线失败（`test_observability_logging_defaults`、`test_validate_config_cli_json_outputs_deterministic_summary`），已用 `git stash` 对照 main 基线确认二者在主分支同样失败（本机环境相关，非本改动引入）
- [ ] 6.3 （人工，待用户在 PR 合并后执行）Jira AAA-8288 按关单判据做生产/预发验证：60s interval 连续 10 次 fire 间隔 ∈ [60,70)s 无累积漂移。自动化层面该判据已由 `test_real_fire_preserves_grid_across_repeated_fires`（真实 store + 真实 `_fire`，5 次连续触发断言网格无漂移）覆盖并纳入 CI 常驻回归；本项是合并后对真实 Slack 环境的最终人工确认，可关闭该 Jira 单
