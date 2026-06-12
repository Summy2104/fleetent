# mgmt-store-hygiene

## Why

实体关系审计（2026-06-12）发现管理库还有两处会咬人的卫生问题：① `agents.tenant_id` 与 `agents.team_id` 双列**无复合一致性**——`team_id` 可指向属于别的 tenant 的 team，而物理路由的主体恰恰取自 `agents.tenant_id`（`materialize.py` 物化进 agent.yaml）、`agent_kbs` 复合键的 tenant 半截也隐含自它：两列一旦矛盾，agent 会把 KB / 共享记忆解析到**错误租户的库文件**，在"物理隔离保合规"的架构里这是最不能错的链路。雪上加霜的是迁移 070 加的全部 FK 在运行时是装饰品（`db.py` 不开 `PRAGMA foreign_keys=ON`，SQLite 默认关）——数据库层没有任何兜底。② `platform.im_gateway_management.identity` 是 blocklist 的同款双权威残渣：`im_users` 已在 Alembic，但 identity.py 仍留 `_init_db` 运行时自建表路径 + `?` 占位符 + `DB_PATH` re-export（`im_user_store` shim 连 `_init_db` 一起 re-export）；且 unify-im-identity-mapping 落地后 `get_or_create` 已上消息热路径，每次解析都白跑一遍 `_init_db`。

## What Changes

- **agents 归属一致性校验（乙1）**：`agent_store.create_agent` / `update_agent_tenancy` 在 `team_id` 非空时校验 `teams.tenant_id == agents.tenant_id`，不一致拒绝（带可诊断错误）；新增管理库一致性审计测试（现存数据全量断言 team↔tenant 一致）
- **identity store 残渣清理**：`platform/im_gateway_management/identity.py` 删 `_init_db` 及全部调用点（含热路径 `get_or_create`）、删 `DB_PATH` re-export、`?` 占位符改 named params；`im_user_store` shim 去 `_init_db` re-export；受影响测试改统一 DB fixture（Alembic 建 schema）
- **文档口径对齐**（`docs/architecture/data-model.md`）：
  - 关系完整性双层口径：管理库 = FK 强制（本 change 起真实生效）+ store 写入校验（FK 表达不了的语义级约束）；agent 侧库 = 约定引用为主、KB 库 FK 级联真实生效
  - 补**跨库引用孤儿语义契约**：物理库间无 FK，消费方 MUST 容忍引用指向已删/已 archive 的管理库实体并按域语义处理（拒/降级，参照 identity-port 的 cron 复检分域模型）
  - `session_meta` 注明仅 playground 会话有行（chat admin 创建路径写入），与 agent 侧 `sessions` 索引职责区分
- **启用 FK 强制（乙2，经实验定界后纳入）**：`db.py` 连接初始化加 `PRAGMA foreign_keys=ON`（全部 SQLite 连接）。实验证据（2026-06-12，本地全量 integration）：FK ON 仅 12 个测试失败、集中 6 个文件、全为 fixture 未种父行；KB/memory/session/approval 测试零失败（agent 侧干净，KB 的两条 `ON DELETE CASCADE` 激活属修复——FK off 时删文档留孤儿 chunk）。配套：
  - `agent_store.delete_agent` 事务内补清 `agent_mcp_server_bindings` / `agent_oauth_bindings` 子行（修复既有孤儿 bug，FK ON 后否则删不掉）
  - `user_store.delete_user` 对"该用户是 team/tenant 审批人"的情况显式预检拒绝（带可诊断错误，FK RESTRICT 语义前移成清晰报错）
  - 修复 12 个测试 fixture（补种父行）

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `tenancy-entities`: 新增（ADDED）"agents 归属一致性"要求——`agents.team_id` 非空时其 team 的 `tenant_id` MUST 与 `agents.tenant_id` 一致，store 写入路径强制
- `im-user-mapping`: 新增（ADDED）"im_users schema 权威为 Alembic"要求——store 不自建表、不 re-export `DB_PATH`、named params（仿 user-blocklist 同款要求）
- `database-runtime`: 新增（ADDED）"FK 强制启用"要求——经 `db.py` 取得的全部 SQLite 连接 MUST 启用 `PRAGMA foreign_keys=ON`；声明了 FK 的库（管理库、KB 库）其约束与级联为真实生效语义
- `agent-definition`: 修改（MODIFIED）"Agent hard deletion"——硬删 SHALL 在同一事务清理 binding 子行（mcp/oauth），不留孤儿

## Impact

- **owning package**：`platform`（agent_store 校验、im_gateway_management/identity 清理）；`im_user_store` shim（顶层 legacy）
- **public API surface**：`create_agent` / `update_agent_tenancy` 签名不变（新增校验异常路径）；`identity.py` 公开函数签名不变；`im_user_store` shim 导出面缩减（去 `_init_db`）
- **owned tables**：无 schema 变更（校验在 store 层；`im_users` schema 已归 Alembic 068 系列）
- **config namespace**：无
- **cross-module dependencies**：无新增；agent/platform 解耦边界不触碰
- **migration / shim plan**：无迁移；`im_user_store` shim 保留其余 re-export 不动
- **相邻切片**：schema-residue-cleanup 与 unify-im-identity-mapping 均已落地归档，无在跑切片冲突；blocklist 改造（schema-residue-cleanup）是 identity.py 清理的直接参照模式
