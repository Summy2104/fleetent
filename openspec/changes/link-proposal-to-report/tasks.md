# link-proposal-to-report Tasks

> 每个实现 task 严格 TDD：先写测试见红，再实现见绿。测试任务在对应实现任务之前。

## 1. schema：reflection_proposals.report_id（嵌入式 Y）

- [ ] 1.1 [测试] integration：最新 Y 版本下 `reflection_proposals` 含 `report_id` 列（可空）；升级路径——以改名前最大版本的库（有存量 proposal 行）migrate-on-open 后列存在、历史行 `report_id` 为 NULL（先红：当前无该列）
- [ ] 1.2 [实现] `runtime/agent_state_migrations.py` 在当前最大版本之后追加新版本（勿硬编码——当前 v31，以实际最大为准）：`ALTER TABLE reflection_proposals ADD COLUMN report_id TEXT` → 1.1 转绿

## 2. 生成与持久化透传 report_id

- [ ] 2.1 [测试] integration：`run_reflection` 从一批 findings 生成 report + memory/skill 提案后，每条落库 proposal 的 `report_id` == 该次 report.id（先红：当前不写）
- [ ] 2.2 [测试] integration：双向追溯——按 report_id 查得其产出的全部 proposal；按 proposal 查得其源 report（先红）
- [ ] 2.3 [测试] unit/integration：无源报告的 proposal（report_id 缺省）落库为 NULL，list/get/apply 不报错（可空语义，先红或现态确认）
- [ ] 2.4 [实现] `reflection/reflection.py`：`ReflectionProposal` 加 `report_id`（默认 None）；`generate_memory_maintenance_proposals` / `generate_skill_proposals` 接收并透传 `report.id`；`_persist_memory_maintenance_proposal` / `_persist_skill_proposal` 的 INSERT 写入 `report_id`；`run_reflection` 中把 `_save_report` 提到 proposals 持久化之前 → 2.1–2.3 转绿

## 3. public API 暴露 report_id

- [ ] 3.1 [测试] integration：proposal 的 list / get 返回结构含 `report_id` 键（有源时为 report id、无源时 None）（先红）
- [ ] 3.2 [实现] proposal list/get/序列化路径补 `report_id` 字段 → 3.1 转绿；全仓 grep proposal 序列化消费点确认无遗漏

## 4. 文档

- [ ] 4.1 `docs/architecture/data-model.md` §3.3：明细图加 `reflection_reports ||--o{ reflection_proposals : "report_id 源报告"` 边；§3.3 实体清单 `reflection_proposals` 描述补 `report_id`（源报告追溯）；note 补一条"proposal 经 `report_id` 追溯到生成它的反思报告（可空：历史/非反思来源行为 NULL）"
- [ ] 4.2 复核 `docs/capabilities/reflection.md` proposal 字段/生命周期描述，有 report_id 缺口则同步

## 5. 收尾

- [ ] 5.1 `make test-pr` 全绿；`uv run pytest tests/integration -q`（不带 `-x`）对照 main 基线无新增失败
- [ ] 5.2 `openspec validate link-proposal-to-report` 通过；所有 checkbox 标记 `[x]`
