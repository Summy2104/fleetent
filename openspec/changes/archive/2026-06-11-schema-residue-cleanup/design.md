# schema-residue-cleanup Design

## Context

持久层重设计（#1–#4）把业务真相源迁出管理库，但 Alembic head 实测（升到 076 后 30 张表）仍残留 4 张零归属表；`blocked_registrations` 从未进过 Alembic，由 `governance/blocklist.py` 运行时 `CREATE TABLE IF NOT EXISTS` 自建——这是 mgmt-tables-into-alembic 收编时的漏网（当时它不在 alembic 也不在文档清单上）；agent 侧 `sessions` 索引带遗留 `agent_name` 列。证据（已逐一核实）：

| 残渣 | 真相源去向 / 取代方案 | 现存引用 |
|---|---|---|
| 管理库 `shared_memory_items` | per-tenant `shared_memory.db`（`memory/shared_memory_migrations.py`） | `memory/shared.py`、`read_projection.py` 均走 tenant 文件，管理库副本零路由 |
| 管理库 `memory_maintenance_proposals` | agent 侧 `reflection_proposals`（Y v25 drop 旧表） | 全仓零引用 |
| 管理库 `skill_proposals` | agent 侧 `reflection_proposals`（Y v26 drop 旧表） | 全仓零引用 |
| 管理库 `skill_hits`（迁移 057） | `skill_hit` trace 事件（`builtin_tools._record_skill_hit` 写）+ `skill_admin_store.list_skill_hit_metrics` 读 trace | 表无人写无人读 |
| `blocked_registrations` 不在 Alembic | 收编（表是活的：`block_service` 写、`user_store.py:263` 查） | `blocklist.py` 自建 + `DB_PATH` re-export + `?` 占位符 |
| `sessions.agent_name`（agent_state.db） | 归属由物理库圈定；platform 跨 agent 语义在管理库 `session_meta.agent_name` | 写入链 `server.py run kwargs → session/manager.py → session/index.py`；无下游读 |

约束：上线前"不迁移数据"窗口仍开（内测环境可重置，但迁移仍须对存量友好）；管理表 Alembic-only、agent 侧嵌入式 Y forward-only；named parameters；不破坏 agent/platform 解耦现状（零反向 import）。

## Goals / Non-Goals

**Goals:**
- 管理库 schema 与"现实归属"一致：杀掉 4 张双真相源误导表
- `blocked_registrations` 回到双权威契约内（Alembic 建表，store 纯 CRUD）
- agent 侧 `sessions` 索引列集合与 per-agent 物理模型自洽（去 `agent_name`）
- 6 个 canonical spec 的同源漂移一并校准；data-model.md 图与表清单对齐实测

**Non-Goals:**
- 不动管理库 `session_meta`（含其 `agent_name`——platform 跨 agent 语义正当）
- 不动 `traces.agent_id`/`tenant_id` 与各 agent 侧表的 `tenant_id` 列（§2 "可换后端 RLS 接缝"豁免）
- 不重构 blocklist 的连接方式（仍经 `user_store._conn` 管理库路径；Identity/store 边界再收紧属后续）
- 不做任何数据迁移/回填（drop 的表均零业务数据归属）

## Decisions

**D1：4 张幽灵表一个迁移（077）drop，`blocked_registrations` 收编单独一个迁移（078）**
拆两个迁移：drop 是纯清理、可独立 review；收编含"幂等承接存量自建表"的特殊语义（存量部署该表可能已存在且有数据）。078 用 `CREATE TABLE IF NOT EXISTS` 等价语义（Alembic 中检查 `inspector.has_table` 再建），列定义与 `blocklist.py:43` 现 DDL 同构，保留存量行。否决合并为一个迁移：语义混杂，回滚粒度差。

**D2：blocklist.py 改造为"纯 CRUD + named params"，连接路径不变**
删 `_init_db` 与 `DB_PATH` re-export（其唯一用途是测试 monkeypatch——测试改为 monkeypatch `user_store` 的连接或用统一 DB fixture）；`?` → named params。否决顺手迁到 `db.py` 句柄注入：blocklist 依赖的 `user_store._conn` 是管理库既定路径，单独换血属 user_store 现代化范畴，不在本切片。

**D3：`sessions.agent_name` 用 Y 新版本 `ALTER TABLE sessions DROP COLUMN agent_name`**
SQLite ≥3.35 原生支持 DROP COLUMN（项目基线满足）；该列无索引、无约束依赖。代码侧：`session/index.py` 的 upsert 列表、`_SELECT_COLS`、行映射去列；`session/manager.py` 保存路径去 `agent_name` 参数（run kwargs 中的 `agent_name` 仍用于 agent 配置解析，与索引无关，不动）。否决"保留列加豁免注记"：列连 RLS 接缝语义都没有，留着就是下一轮审计的噪音。

**D4：spec 漂移修复随本 change 走 delta，不另开 change**
6 个 capability 的漂移全部由本 change 触碰的表/列直接牵出（同一爆炸半径），分拆只会制造第二个微型 change 和归档顺序依赖。

**D5：管理库 schema 断言测试落 integration 一份"全量表清单对账"**
新增（或扩展既有）integration 测试：alembic 升到 head 后断言 4 表不存在、`blocked_registrations` 存在且列同构——这是对"双真相源回归"的结构性防御，比逐表零散断言更抗腐化。agent 侧同理：打开最新 Y 后断言 `sessions` 无 `agent_name` 列。

## Risks / Trade-offs

- [存量部署 `blocked_registrations` 列序/约束与 078 定义有微差] → 078 以 `has_table` 短路，不重建不校列；列同构性由 store 既有 DDL 与迁移共用同一份列定义保证（实现时从 blocklist.py 现 DDL 抄列）
- [`sessions` DROP COLUMN 在旧 SQLite 上失败] → 项目运行基线 Python 3.12 自带 SQLite ≥3.45；迁移加版本前置检查无必要
- [未知的 `agent_name` 消费方漏网] → apply 时全仓 grep `agent_name` 复核（区分 run-kwargs/agent-config 用途与索引列用途）；platform 读投影只用 `count_with_db`，已核实
- [`skill_hits` 未来想要表级指标] → trace 事件保留全量原始数据，可随时物化；删表不损失信息

## Migration Plan

1. Alembic 077：`drop_table` ×4（downgrade 重建空表，列定义按 057/068 原 DDL）
2. Alembic 078：`blocked_registrations` 收编（`has_table` 幂等）
3. agent_state Y 新版本：`ALTER TABLE sessions DROP COLUMN agent_name`（forward-only，无 downgrade）
4. 代码：blocklist.py 去自建/去 re-export/named params；session index/manager 去列
5. 文档：data-model.md §3.1/§3.2/§3.3 按 proposal ④ 修补

回滚：077/078 有 downgrade；Y forward-only 不回滚（内测窗口可重置库）。

## Open Questions

（无——三个口径已由用户拍板：删 agent_name 列、收编 blocklist、文档随本 change 修。）
