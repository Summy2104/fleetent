# mgmt-store-hygiene Tasks

> 每个实现 task 严格 TDD：先写测试见红，再实现见绿。测试任务在对应实现任务之前。

## 1. agents 归属一致性校验（乙1）

- [x] 1.1 [测试] integration：`create_agent(tenant_id=T1, team_id=属于T2的team)` 被拒、`agents` 无新行；`update_agent_tenancy` 跨租户改属被拒、原行不变；`team_id` 为空时两函数照常写入（先红：当前零校验）
- [x] 1.2 [测试] integration：常驻一致性审计——现存全量 `agents` 行（team_id 非空者）JOIN `teams` 断言 tenant 一致（先确认在测试库恒绿、语义正确）
- [x] 1.3 [实现] `agent_store.create_agent` / `update_agent_tenancy` 加 team↔tenant 校验（错误信息含 agent、team、两侧 tenant；错误类型对齐 agent_store 既有风格）→ 1.1 转绿

## 2. identity store 残渣清理

- [x] 2.1 [测试] unit：守护测试——`platform/im_gateway_management/identity.py` 源码无 `CREATE TABLE`、无 `_init_db`、无 `DB_PATH` re-export、无 `?` 占位符；`fleetent.im_user_store` 不再导出 `_init_db`（先红）
- [x] 2.2 [测试] integration：经 Alembic 建好 schema 的库上 `get_or_create` / `approve_user` / `block_user` / `list_all` / `list_pending` / `check_allowed_by_user_id` 行为不变；`get_or_create` 调用路径不执行任何 schema 检查语句（以 2.1 红为 TDD 锚）
- [x] 2.3 [实现] `identity.py`：删 `_init_db` 函数与全部调用点、删 `DB_PATH` re-export、`?` 改 named params；`im_user_store` shim 删 `_init_db` re-export；受影响测试改统一 DB fixture（参照 schema-residue-cleanup 对 blocklist 的处理）→ 2.1/2.2 转绿
- [x] 2.4 [核实] 全仓 grep `_init_db`（im_gateway_management 相关）与 `im_user_store.DB_PATH` 消费方清零（预期仅测试，发现业务消费即按注入/fixture 改造）

## 3. FK 强制启用（乙2）

- [x] 3.1 [测试] integration：经 `db.py` 打开的连接 `PRAGMA foreign_keys` 返回 1；插入 `tenant_id` 不存在的 `agents` 行报 FK 错误不产生孤儿行（先红：当前 pragma 未开）
- [x] 3.2 [测试] integration：`delete_agent` 对持有 mcp/oauth binding 的 agent——FK ON 下成功删除且 binding 子行同事务清空（先红：当前不清子行，FK ON 后会报约束错误）
- [x] 3.3 [测试] integration：`delete_user` 对"是 team 或 tenant 审批人"的用户被预检拒绝（可诊断错误指明所任审批人位置）；非审批人用户照常删除（先红）
- [x] 3.4 [测试] integration：KB 级联——删除 `knowledge_documents` 行后其 `knowledge_chunks` 随级联消失（FK ON 激活 `ON DELETE CASCADE`；先确认 FK off 基线下该行为缺失或由代码显式删除）
- [x] 3.5 [实现] `db.py` 连接初始化加 `PRAGMA foreign_keys=ON`；`agent_store.delete_agent` 事务内补清 `agent_mcp_server_bindings` / `agent_oauth_bindings`；`user_store.delete_user` 加审批人预检 → 3.1–3.4 转绿
- [x] 3.6 [实现] 修复实验已定位的 12 个 fixture 失败（6 文件：`test_long_term_ctx_policy_store` / `test_long_term_ctx_policy_resolution` / `test_agent_oauth_binding_store` / `test_agent_store` / `test_agent_materialize_export` / `test_drop_dead_kb_binding_path_safety`——补种父行），全量 integration 无新增失败

## 4. 文档口径对齐

- [x] 4.1 `docs/architecture/data-model.md` §2：关系完整性双层口径——管理库 = FK 强制（本 change 起真实生效）+ store 写入校验（FK 表达不了的语义级约束，如 team↔tenant 复合一致性）；agent 侧库 = 约定引用为主、KB 库 FK 级联真实生效；注明 FK 启用不回扫存量行（迟发报错语义）
- [x] 4.2 `docs/architecture/data-model.md`：补跨库引用孤儿语义契约（物理库间无 FK，消费方 MUST 容忍引用指向已删/已 archive 实体并按域语义处理：拒/降级，参照 identity-port 的 cron 复检分域模型）；`session_meta` 注明仅 playground 会话有行（chat admin 创建路径写入）、与 agent 侧 `sessions` 索引职责区分
- [x] 4.3 复核 `docs/records/decision-logs/persistence-redesign-decisions.md` 追记一条"FK 强制启用 + store 校验双层语义（乙1/乙2）"决策（一句话级，不展开）

## 5. 收尾

- [x] 5.1 `make test-pr` 全绿；`uv run pytest tests/integration -q`（不带 `-x`）对照 main 基线无新增失败
- [x] 5.2 `openspec validate mgmt-store-hygiene` 通过；所有 checkbox 标记 `[x]`
