# Tasks — cron-delivery-governance

> 每个实现 task 严格 TDD：先写测试见红 → 实现见绿。测试任务一律在对应实现任务之前。

## 1. half-set 投递参数拒绝

- [x] 1.1 写测试：只给 `notify_target`（缺 `notify_platform`）→ 工具返回明确 error、不创建任务；反向同理；成对提供 → 正常创建（`tests/integration/test_tools_schedule.py` 新用例）→ 见红
- [x] 1.2 实现：schedule 工具 create 分支组装 `deliver` 前校验成对性（design D1）→ 见绿

## 2. generate 目标可解析性——从「创建时硬拒绝」改为「回执警示」（design D2 二次修正）

> 原计划 2.1（grep）已完成并记录结论：`schedule_store.create`/`cron_scheduler.create_task` 的唯一生产调用点是 `schedule` 工具本身；但工具层硬拒绝仍会打断 `test_tools_schedule.py` 内 7 个与投递目标无关的既有测试（返回 id、live 注册、pause/resume/remove、owner stamping、degrade 文案）。改为创建回执警示（不阻断创建），零测试破坏面——见 design D2、proposal「实现期调整」。原 2.1/2.2/2.3 已作废，并入下方任务 3。

## 3. create 回执明示/警示投递目标

- [x] 3.1 写测试：显式目标创建 → 回执含 `slack:C123(channel)`；origin 回落创建 → 回执写明投递回创建会话；**无 origin 且无显式目标的 generate** → 回执含无法送达的警示；**action 任务**无目标 → 回执不含该警示（`tests/integration/test_tools_schedule.py` 新用例）→ 见红
- [x] 3.2 实现：create 成功回执追加目标描述/警示（design D4，不动既有前缀文案）→ 见绿

## 4. fired run 排除 schedule 工具

- [x] 4.1 写测试：`_filter_outbound_tools` 新增 `exclude` 参数（独立于 suppress）单测；generate/action fire 经 `_agent_run` 均传 `exclude_tools=frozenset({"schedule"})`（`tests/unit/test_generate_fire_suppresses_outbound.py` 新用例）→ 见红
- [x] 4.2 实现：`loop._filter_outbound_tools`/`run`/`_run_inner` 增加 `exclude_tools` 参数（新增正交参数，不改动既有 `suppress_outbound_tools` 语义/调用方）；`cron_scheduler._agent_run` 固定传 `exclude_tools={"schedule"}`（design D3，实现比原计划更简单：不是把 suppress 机制参数化，而是新增一个独立排除集）→ 见绿
- [x] 4.3 跑受影响层：`tests/integration/test_cron_*`、`test_typed_scheduled_tasks.py`、`test_cron_typed_dispatch.py` 与 loop 抑制相关 unit 无新增失败（467 passed）

## 5. 文档与收尾

- [x] 5.1 更新 `docs/capabilities/scheduling.md`：目标成对配置、回执明示/警示、fired run 无 schedule 工具三节 + 场景 11-13（注：本 change 分支尚未同步已合并的 change-1 main，场景编号在同步 main 时需与 change-1 新增的场景 11/12 重排，避免重复编号）
- [x] 5.2 change 收尾：`make test-pr`（unit 4303 passed + 层边界检查 + 改动文件 ruff format/check 全绿）+ `make test-integration-ci`（2291 passed, 1 skipped）无新增失败——各命中同一个与本改动无关的预置基线失败（`test_observability_logging_defaults`、`test_validate_config_cli_json_outputs_deterministic_summary`，与 change-1 观测到的完全一致，已确认为本机环境相关）
- [ ] 5.3 （人工，待用户在 PR 合并后执行）Slack 实测：half-set 创建被拒的用户体验、回执目标显示（对照 AAA-8279 报告场景）
