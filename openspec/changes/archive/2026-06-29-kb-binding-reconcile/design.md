## Context

`materialize._knowledge_for_agent` 从 `agent_kbs` 一次性生成 agent.yaml 的 `knowledge.bindings`(全部用 `agent.tenant_id`)。`long_term_ctx._search_knowledge` 读 agent.yaml 快照,且取 `bindings[0].tenant_id`。node reconcile(`node/reconcile.py`)已有按 home-hash 检测变更重写 home 的机制,并有 `resync_epoch` 强制 resync 范式(skills backflow,迁移 103)。`kb-agent-binding` spec 的 "Bound KBs are queryable per agent" 在解耦约束下应理解为"materialized 快照反映 store",非 agent 运行时 live 查询。

## Goals / Non-Goals

**Goals:**
- bind/unbind 后运行中 agent 的 bindings 经 reconcile 刷新,session 边界生效。
- 单租户不变量显式校验,消除 `bindings[0].tenant_id` 未守护假设。

**Non-Goals:**
- 不让运行时 long-term-ctx 直接查 `agent_kbs`(违反解耦,且 `kb-agent-binding` 的真相源语义由 materialize 快照承接)。
- 不做 session 中途热改 KB 范围。
- 不改 binding 管理 API、`agent_kbs` 表、注入/预算语义。

## Decisions

### 决策:复用 skills 的 resync_epoch + reconcile 范式,不另造机制
- bind/unbind 改 `agent_kbs` 时,platform 标记受影响 agent 需 resync(复用/对齐现有 `resync_epoch` 信号);node reconcile 每 tick 据此重 materialize 该 agent home(沿用 `_current_home_hash` / `_write_home` 路径)。
- **为什么**:skills backflow→resync 已是同构的"管理面变更→reconcile 重 materialize→agent 采用"链路;复用降低新机制风险与认知负担。
- **epoch 维度**:优先复用现有 resync 信号;若需把 knowledge 与 skills 分开触发,加独立 epoch 列(Alembic forward-only)。实现阶段定,不阻塞 propose。

### 决策:session 边界 reload,不中途热改
- agent 在新 session/对话开始时读取(可能已被 reconcile 更新的)agent.yaml bindings。进行中的对话保持其起始 KB 范围。
- **为什么**:避免一次对话内 KB 可见范围突变导致的不一致召回与审计困惑。

### 决策:单租户不变量在 materialize + load 两处校验
- materialize 本就全用 `agent.tenant_id`(天然单租户);load 端补校验,守护手工编辑 / 异常数据。违反 fail loudly。`long_term_ctx` 可据此安全使用统一 tenant,移除"取第一个"的脆弱假设。

## Risks / Trade-offs

- **[reconcile 延迟]** bind 到生效有 reconcile tick + session 边界两段延迟。**Mitigation**:可接受(KB 范围非实时);文档说明"绑定变更下个会话生效"。
- **[长会话不更新]** 超长 session 期间绑定变更不生效。**Mitigation**:符合"session 边界生效"设计;如需更强,后续可加显式刷新点,不在本 change。
- **[解耦回归]** 误把运行时改成查 `agent_kbs`。**Mitigation**:spec scenario "Running agent does not query agent_kbs directly" + module-boundaries 护栏覆盖。

## Migration Plan

- 优先复用现有 resync 信号 → 无新 schema。若加独立 knowledge epoch 列,走 Alembic 管理库 forward-only 迁移。
- 部署即生效;存量 drift 在下次 reconcile + session 边界自然收敛。回滚还原代码。

## Open Questions

- knowledge 是否需要独立于 skills 的 resync epoch:实现阶段按是否会产生过度 re-materialize 噪声决定。
