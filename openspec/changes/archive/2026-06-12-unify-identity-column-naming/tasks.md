# unify-identity-column-naming Tasks

> 每个实现 task 严格 TDD：先写测试见红，再实现见绿。测试任务在对应实现任务之前。

## 1. 列改名（嵌入式 Y 新版本）

- [x] 1.1 [测试] integration：最新 Y 版本下 `approvals` 表含 `approver_user_id` 列、不含 `approver_actor` 列；升级路径——以改名前最大版本的库（`approver_actor` 已填值的行）migrate-on-open 后列改名、历史值原样保留（先红：当前列名为 approver_actor）
- [x] 1.2 [实现] `runtime/agent_state_migrations.py` 在当前最大版本之后追加新版本（勿硬编码——v29/v30 已被 typed-scheduled-task-delivery 占用）：`ALTER TABLE approvals RENAME COLUMN approver_actor TO approver_user_id` → 1.1 转绿

## 2. 代码与测试同步

- [x] 2.1 [测试] unit：守护测试——`governance/approval_store.py` 与 `governance/permission_gate.py` 源码无字符串 `approver_actor`（先红）
- [x] 2.2 [测试→实现] `approval_store.py`（SELECT 列、named params、返回键）与 `permission_gate.py`（写入参数）改名；5 个测试文件（`test_approval_store` / `test_permission_gate` / `test_permission_gate_restart` / `test_standalone_approval` / `test_per_agent_approvals_schema`）同步断言新列名/键名 → 2.1 转绿，相关测试无新增失败
- [x] 2.3 [核实] standalone `/approvals` 端点响应字段若透出该键，确认改名后契约有测试覆盖；全仓 grep `approver_actor` 清零（src / tests / docs，openspec/changes 归档历史除外）

## 3. 文档（data-model.md §3.3）

- [x] 3.1 「actor 为不透明标签」措辞改为统一身份列语义契约：agent 侧所有 `*_user_id` 列 = Principal.user_id 字符串（managed=内部 `users.id` / standalone=渠道原生 id / 基础设施=`system`），无 FK、跨库 opaque
- [x] 3.2 同节补四条语义注记：`reflection_proposals.target_ref` 多态引用（memory→`memory_items.id`、skill→文件系统 skill 名，完整性由 apply 路径兜底）；`sub_agent_runs.run_id` 与 `traces.run_id` 同命名空间；库内 `session_id` 约定引用、无时序保证（approvals 行可先于 `sessions` 索引行）；`budget_usage` scope 枚举 `task|session|user|agent`（key 语义随 scope）

## 4. 收尾

- [x] 4.1 `make test-pr` 全绿；`uv run pytest tests/integration -q`（不带 `-x`）对照 main 基线无新增失败
- [x] 4.2 `openspec validate unify-identity-column-naming` 通过；所有 checkbox 标记 `[x]`
