# approvals-schema-drift-hotfix — Design

## Context

- `governance/approval_store.py` 是 `approvals` 表的 agent 侧 schema owner（模块 docstring 明示 "Schema owner: this module — not Alembic"），`ensure_schema()` 用 `CREATE TABLE IF NOT EXISTS` 自建，DDL 含 `approver_actor TEXT`。
- 野外存在三种表形态：
  | 形态 | 来源 | 列特征 |
  |------|------|--------|
  | O（旧） | v0.2.0 等存量部署 / `alembic upgrade head`（001 定义） | 仅 `approver_user_id`，无 `approver_actor` |
  | N（新） | 当前 main 的 `ensure_schema` 新建 | 仅 `approver_actor`，无 `approver_user_id` |
  | B（双列） | 形态 O 手动 `ALTER` 止血后 | 两列都有 |
- 形态 O 上，`update_approval` 的 `UPDATE ... SET approver_actor = ...` 抛 `no such column`，审批 resolve 永远失败（已在 2026-06-10 真实 Slack e2e 复现）。
- approvals 不在 `agent-db-schema-self-init` 漂移护栏清单（traces/memory/reflection）内，alembic（旧列）↔ agent 侧（新列）分叉无护栏捕获——这是漂移得以发生的制度原因，制度修复属 3b-4。
- pending change `per-agent-approvals-lib`（3b-4，0/9 未动工）将把 approvals DDL lift 进 per-agent `agent_state.db` 统一迁移列表 `runtime/agent_state_migrations.py` 并 drop alembic 定义；其前置 3b-1（`agent_scope` / 统一列表）已在 main。

## Goals / Non-Goals

**Goals:**

- 存量形态 O 的库在下一次 `ensure_schema()` 时自愈：补 `approver_actor` 列并回填历史审批人数据，审批 resolve 恢复可用。
- 形态 N / B 与新建库零行为变化；重复调用幂等。
- 改动收敛在 `approval_store.ensure_schema` 单函数，3b-4 替换时可整体丢弃。

**Non-Goals:**

- 不把 approvals 迁入嵌入式迁移引擎（Y）——全局 `fleetent.db` 无统一 MIGRATIONS 列表，为单表另立 `user_version` 戳违反 one-file-one-stamp 原则（见 `runtime/agent_state_migrations.py` 头注释），且 3b-4 落地即拆。
- 不动 alembic、不删 `approver_user_id` 旧列、不实现 platform 只读投影（均属 3b-4 及后续切片）。
- 不把 approvals 纳入漂移护栏清单（护栏是过渡件，3b-4 后 approvals 退出双权威）。

## Decisions

### D1：ensure_schema 内探测补列，而非嵌入式迁移引擎

- **选定**：`ensure_schema()` 在 `CREATE TABLE IF NOT EXISTS` 后，用 `PRAGMA table_info(approvals)` 探测 `approver_actor`；缺失则 `ALTER TABLE approvals ADD COLUMN approver_actor TEXT`。
- **备选 1（曾被推荐，后否决）**：approval_store 独立 `MIGRATIONS` + `schema_migrations.migrate()`。否决理由：(a) 全局 `fleetent.db` 上独立 `user_version` 戳与 one-file-one-stamp 原则冲突，将来任何第二个想在该库用 Y 的 store 都会相撞；(b) 需要 baseline 收编步（探测三种形态 stamp 版本），复杂度远超一次列探测；(c) 3b-4 落地时整套机制被拆，临时基础设施过度设计。
- **备选 2**：等 3b-4 一并解决。否决理由：3b-4 未动工且范围大（alembic drop、agent_app 接线、allowlist），生产 bug 等不起；且 3b-4 「上线前不迁移数据」，本就不覆盖存量全局库的漂移修复。

### D2：回填只在「本次补列」分支内执行

- **选定**：仅当探测到缺列并实际执行了 `ALTER` 后，才执行 `UPDATE approvals SET approver_actor = approver_user_id WHERE approver_actor IS NULL`。
- **理由**：补列发生 ⇔ 表是形态 O ⇔ `approver_user_id` 必然存在，UPDATE 不会引用不存在的列。若无条件回填，形态 N 的库（无 `approver_user_id`）会抛 `no such column`——把修一个漂移变成造一个新崩溃。
- **代价（接受）**：形态 B（手动止血过的库）不回填——其 `approver_actor` 为 NULL 的历史行保持 NULL。该形态只存在于手动干预过的库，历史审批人是审计性数据，缺失可接受。

### D3：探测用 PRAGMA table_info，经现有 db.py 边界

- 列探测走 `SQLiteDatabase` 现有查询接口执行 `PRAGMA table_info(approvals)`，不新增裸 `sqlite3.connect`，与「绕过统一 db.py 边界」禁令一致。

## Risks / Trade-offs

- [并发首调竞态：两个进程同时探测到缺列、同时 ALTER，后者抛 duplicate column] → `ensure_schema` 捕获该特定 `OperationalError`（message 含 `duplicate column`）并视为已自愈（另一进程已完成），不吞其它异常。实际部署为单 daemon 进程，竞态概率极低，此为防御性处理。
- [hotfix 与 3b-4 的窗口期内，alembic 侧 approvals 定义仍是旧形态] → 接受：alembic 建出的形态 O 表会被本补丁在首次 `ensure_schema()` 时自愈，路径自洽；唯一真相源收敛由 3b-4 完成。
- [ensure_schema 每次操作前都被调用，PRAGMA 探测有微小开销] → PRAGMA table_info 是元数据读，开销与现状的 CREATE IF NOT EXISTS 同级，可忽略。

## Migration Plan

1. 合入后，存量部署升级二进制即自愈（首次审批操作触发 `ensure_schema`），无需手动 DDL、无需重启顺序要求。
2. 回滚：revert commit 即可——已补的列是可空附加列，旧代码（引用 `approver_actor` 的当前 main）与新列共存无碍；更旧代码（引用 `approver_user_id`）该列仍在。
3. 3b-4 落地时：删除本补丁逻辑（随 `ensure_schema` 整体替换），无独立清理步骤。

## Open Questions

（无——方案已与 2026-06-10 线上止血实操对齐，三种形态行为均有测试覆盖计划。）
