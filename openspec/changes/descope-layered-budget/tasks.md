# descope-layered-budget Tasks

> 删除类 change 的 TDD：先改/删覆盖被删功能的测试 + 写守护断言（功能/表/配置字段已不存在）见红，再删实现见绿。守护测试在删实现之前。

## 1. 表退役（嵌入式 Y DROP）

- [ ] 1.1 [测试] integration：最新 Y 版本下 `agent_state.db` **不含** `budget_usage` 表；升级路径——含 `budget_usage`（可有存量行）的旧库 migrate-on-open 后该表被 drop（先红：当前表存在）
- [ ] 1.2 [实现] `agent_state_migrations.py` 在当前最大版本之后追加新版本 `DROP TABLE budget_usage`（历史 CREATE 行保留，勿硬编码版本号）→ 1.1 转绿；删 `test_budget_usage_migration` 中已失效的建表断言

## 2. 配置字段移除（两处 GovernanceConfig）

- [ ] 2.1 [测试] unit：守护——`agent_config.GovernanceConfig` 与 `runtime/snapshot.GovernanceConfig` 均**无** 8 个 `agent_budget_*` 字段；带 `agent_budget_*` 键的 agent.yaml 仍能加载不报错（未知键宽容）；`agent_max_turns`/`agent_max_tokens`/`agent_grace_*`（AR2）仍在（先红）
- [ ] 2.2 [实现] 两处 GovernanceConfig 删 8 个 `agent_budget_*` 字段及 `_governance_from_file` 等读取点 → 2.1 转绿；调整 `test_agent_config_governance` 去掉 layered 字段断言

## 3. 模块与接线删除

- [ ] 3.1 [测试] unit：守护——`fleetent.runtime.layered_budget` 不可导入（模块已删）；`loop.py` 无 `_setup_layered_budget`/`_layered_budget_add`；`agent_app.py` 无 `layered_budget` 引用（先红）
- [ ] 3.2 [实现] 删 `runtime/layered_budget.py`；删 `loop.py` 的 `_setup_layered_budget`/`_layered_budget_add` 及调用点（保留 AR2 per-run budget 接线不动）；删 `agent_app.py` 的 import + `set_state_db`；删测试 `test_layered_budget` / `test_layered_budget_per_agent` / `test_layered_budget_store` → 3.1 转绿
- [ ] 3.3 [测试→实现] 守护——AR2 per-run budget 仍生效：单次运行超 `agent_max_turns`/`agent_max_tokens` 仍触发 `budget_exceeded` + Grace Call（确认误删边界，应现绿/无新增失败）

## 4. example 与文档

- [ ] 4.1 `agents/default/agent.yaml.example`：删 layered budget 段（`agent_budget_*` 行）+ 头部注释里的 `agent_budget_*` 提及；确认删后该 example 仍能被 `AgentFile` 加载（若有 example 校验测试，跑过）
- [ ] 4.2 `docs/architecture/data-model.md`：§3.1 宏观图去 `budget_usage` 节点；§3.3 表清单 **"11 张表"→"10 张表"**、删实体描述里的 `budget_usage`、删图中 `budget_usage {…}` 块、删 note ④（budget scope 枚举那条，其余 note 顺序/编号相应调整）
- [ ] 4.3 `docs/records/decision-logs/`：追记 descope 决策（为什么砍：opt-in 默认休眠 pilot 无人用 + 语义/TTL 缺口；AR2 per-run 保留；将来怎么加回：从 git 历史取完整设计）；复核 `docs/capabilities/`（agent-runtime / governance）有无 layered budget 描述需同步

## 5. 收尾

- [ ] 5.1 `make test-pr` 全绿；`uv run pytest tests/integration -q`（不带 `-x`）对照 main 基线无新增失败
- [ ] 5.2 全仓 grep `layered_budget` / `budget_usage` / `agent_budget_` / `BudgetScope` / `BudgetWindow` 清零（迁移历史的 DROP/历史 CREATE 与 openspec 归档除外）
- [ ] 5.3 `openspec validate descope-layered-budget` 通过；所有 checkbox 标记 `[x]`
