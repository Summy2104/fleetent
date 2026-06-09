## Context

2026-06-09 排查澄清两件易混淆的事实：

1. **迁移链是健康的**：空库 `alembic upgrade head` 干净跑到 062（含 049 drop_agent_templates）。
   之前误判「链坏了」，是因为 `env.py` 忽略 `DATABASE_URL`，命令实际打在真实 `data/fleetent.db`
   上——而该库 schema 已偏离迁移历史（混合 `_init_db` + 部分 alembic + stamp 拼出），并非迁移代码问题。
2. **双 schema 权威是有意设计**：单机 agent（`fleetent agent run`）必须脱离 platform/alembic 启动，
   故 per-agent 库由各 store 的 `ensure_schema()` 自建；管理库由 alembic 升级。`agent-db-schema-init`
   change 已落地此设计，并以「ensure_schema DDL 与 migrations DDL 保持字段一致」为约束——但靠手工。

## Decisions

- **保留双权威，不合并**：合并到「alembic 单一源」会破坏单机 agent（它不能依赖 alembic）。
- **手工一致 → 自动护栏**：新增漂移护栏测试，把「保持字段一致」从约定升级为 CI 可校验的硬约束。
- **env.py 取 app 配置 URL**：消除「app 与迁移指向不同库」的隐患，也避免重演本次误操作真实库。
- **厘清「无裸建表」边界**：`db-migration` 的「No raw schema creation」适用于**管理表**（仅 alembic）；
  **agent-side 表**因单机约束允许 `ensure_schema`，但须与 alembic 一致（护栏强制）。`session/index` 的
  `sessions` 属 agent-side 会话元数据，迁到统一 `db.py` + `ensure_schema`，消灭 `users.db` 与裸 sqlite3。

## 漂移护栏形态

空临时库两路建 schema：(a) `alembic upgrade head`；(b) 调用全部 `ensure_schema()`。
对 (b) 创建的每张表，断言其列集合 == (a) 中同名表的列集合。
**teeth 验证**：临时扰动某 `ensure_schema` 的列定义 → 护栏必须转红；恢复后转绿。
（与既有 `tests/unit/test_module_dependency_guardrails.py` 的护栏思路一致。）

## 不做什么

不在本期碰：管理表收编 alembic、三层库分离、vector 库改名、Identity 端口。理由见 proposal「Out of scope」。
本期只做「不退步的地基」：URL 归一、漂移护栏、消灭 users.db、文档对齐。
