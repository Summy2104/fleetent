# mgmt-store-hygiene Design

## Context

实体关系审计核实的事实：`agents` 表双列各有独立 FK（迁移 070：`fk_agents_tenant`、`fk_agents_team`）但无复合一致性；`db.py` 连接初始化只设 WAL + busy_timeout，**不开 `PRAGMA foreign_keys=ON`** → 070 的全部 FK 运行时不生效；`update_agent_tenancy`（agent_store.py:211）双列直写零校验；`materialize.py:99` 把 `agent.tenant_id` 物化进 agent.yaml 作物理路由主体。identity.py：`_init_db` 在每个公开函数入口调用（含 `get_or_create`，unify-im-identity-mapping 后已上消息热路径）、`?` 占位符、`DB_PATH` re-export（im_user_store shim 转 re-export）。直接参照：schema-residue-cleanup 对 `governance/blocklist.py` 的同款改造（删自建 + named params + 测试改 fixture）已落地，模式可抄。

## Goals / Non-Goals

**Goals:**
- agents 的 team↔tenant 矛盾在写入时被拒（物理路由正确性护栏前移到 store 层）
- identity.py 回到双权威契约内：Alembic 建 schema，store 纯 CRUD；热路径不再每次跑建表检查
- data-model.md 的 FK / 孤儿语义 / session_meta 口径与实测一致

**Non-Goals:**
- 不补复合 FK（`FOREIGN KEY (team_id, tenant_id) REFERENCES teams(id, tenant_id)`）：需要 `teams UNIQUE(id, tenant_id)` + batch 重建表，复合一致性已由 store 校验覆盖，收益不抵迁移复杂度；FK ON 后如将来要 DB 级双保险再议
- 不改 `delete_user` 的存在性（hard delete 与"archive 优先"哲学的张力属身份生命周期议题，本 change 只给审批人引用加预检拒绝）
- 不动 agent-definition spec 的 Schema 要求陈旧问题（未列 tenant_id/team_id 列——历史快照式要求，留给下次触碰该 spec 时对齐）
- 不迁移/不修存量数据（审计测试若发现不一致行，如实上报再定）

## Decisions

**D1：校验放 store 层（`create_agent` / `update_agent_tenancy`），不放 admin API 层**
所有写路径都收口在这两个函数（admin API / CLI / provisioning 都经它们）；放 API 层会漏 CLI。校验 = `team_id` 非空时单查 `teams.tenant_id` 比对，不一致抛带上下文的 `ValueError`（或项目既有错误类型，apply 时对齐 agent_store 的错误风格）。

**D2：identity.py 改造完全复制 blocklist 模式**
删 `_init_db` 函数与全部调用点；`?` → named params；删 `DB_PATH` re-export。`im_user_store` shim 只删 `_init_db` 行、其余 re-export 不动（仍有 admin 面消费）。测试改用统一 DB fixture（Alembic 建 schema）——blocklist 改造的测试处理可直接参照。

**D3：审计测试常驻（不是一次性脚本）**
"存量 agents 行 team↔tenant 一致"做成 integration 常驻断言（空库/测试库恒真，真实库回归时兜底），与 schema-residue-cleanup 的"管理库表清单对账"测试同属结构性防御。

**D4：纳入乙2——`PRAGMA foreign_keys=ON` 全连接启用（经实验定界，推翻最初 deferred 判断）**
实验（2026-06-12 本地，patch db.py 跑全量 integration）：12 failed / 1914 passed，失败集中 6 个文件、全为 fixture 未种父行（ltc_policies→tenants、oauth_bindings→agents、agent_store/materialize/kb-binding-path fixture）；基线回归确认该 81 个测试 FK off 全绿。KB/memory/session/approval 零失败——agent 侧库干净，KB 的 `ON DELETE CASCADE` 激活属修复（FK off 时删 `knowledge_documents` 留孤儿 `knowledge_chunks`）。head FK 面仅 8 条 / 7 表（073–077 drop 后大幅缩小）。结论：有界小活，且与乙1 合成完整主题"关系完整性从装饰变真实"（store 校验 + FK 强制双层）。配套两处删除路径：`delete_agent` 事务内补清 mcp/oauth binding 子行（修既有孤儿 bug）；`delete_user` 预检"是 team/tenant 审批人"则拒（把 FK 的晚期约束错误前移成可诊断报错，管理员须先改任审批人）。注意 FK 强制是 per-connection 的：只改 `db.py` 单点即覆盖全部经边界的连接；`vector_store/backend.py` 的 aiosqlite 连接无 FK 声明，不需要动。

**D5：文档把"store 校验 + FK 强制"钦定为关系完整性的双层现行语义**
data-model.md §2/§3 写明：管理库 = FK 强制（本 change 起生效）+ store 写入校验（语义级，如 team↔tenant 复合一致性 FK 表达不了）；agent 侧库 = 约定引用为主、KB 库 FK 级联真实生效；跨库引用无 FK、消费方 MUST 容忍指向已删/已 archive 实体并按域语义处理（拒/降级）。避免下一轮审计再把"FK 没开"当新发现。

## Risks / Trade-offs

- [存量库已有 team↔tenant 不一致行] → 审计测试会暴露；本 change 不静默修数据，发现即上报用户定夺
- [校验多一次单行查询在 agent 创建/改属路径] → 管理操作低频，可忽略
- [删 `_init_db` 后某条测试路径依赖自建表] → blocklist 改造已趟过同款（统一 fixture），照搬
- [im_user_store shim 仍有 `_init_db` 外部消费方] → apply 时全仓 grep 核实（预期只有测试）
- [FK ON 后存量**部署**库有违规行] → SQLite 启用 FK 不回扫存量行，只拦后续写；触碰违规行的 update/delete 会迟发地报错——可接受（上线前窗口，内测库可重置），data-model 文档注明
- [实验之外仍有漏网测试/路径在 FK ON 下失败] → 实验跑的是全量 integration；unit 层 mock DB 不受影响；apply 收尾的全量基线对照是最终防线
- [`db.py` 之外的裸连接没拿到 pragma] → retire-raw-sqlite-connect 已收口裸 `sqlite3.connect`；alembic env 的迁移连接独立于运行时（迁移自身不依赖 FK off 的行为，077/078 为 drop/create）

## Migration Plan

无 schema 迁移、无数据迁移。`foreign_keys=ON` 随代码部署对新连接生效；回滚 = revert 代码（FK 退回不强制，无数据影响）。

## Open Questions

（无——乙1/乙2 均已与用户对齐纳入本 change；复合 FK 与 delete_user 生命周期张力记入 Non-Goals。）
