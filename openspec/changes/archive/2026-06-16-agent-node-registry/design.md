## Context

分机编排序列的数据基座。今天管理库（Alembic 维护）已有 `agents`(INTEGER id PK)、`api_keys`(key_hash 哈希存储)、`agent_admin_state`(agent_id INTEGER PK + FK CASCADE) 等。本 change 加两张管理表与最小入口，**无运行时行为**——node 注册表 + agent→node 显式 pin，供 C2 的分区期望态消费。

## Goals / Non-Goals

**Goals:**
- 立 `nodes` + `agent_placements` 两张管理表（Alembic forward-only）。
- node 手动登记：mint `ma-<hex>` service key、仅哈希持久化、可解析为 node 身份。
- agent→node 1:1 显式 pin / unpin / 查询。
- `fleetent-admin node register|list|deregister` 运维入口 + pin/unpin 入口。

**Non-Goals:**
- 不消费 status、不产期望态、不下发配置/secret（C2/C4）。
- 不做 node 侧任何东西（C3）。
- 不做 label 匹配调度、failover、auto-schedule（roadmap）。
- 不碰 `data-model.md`、主 specs。

## Decisions

1. **node-id 用运维选定的 TEXT 主键**（如 `node-eu-1`），不用自增 INTEGER——node 是人面对的基础设施单元，稳定可读的 slug 比代理键友好；与 agent 的 (INTEGER id + name) 不同，node 无"可变标签 vs 不可变身份"需求，单一 slug 足够。

2. **service key 复用 `ma-` + key_hash 模式，但落在 `nodes` 表，不进 `api_keys`**：node 不是 User（身份模型"一切是 User"针对人/主体；node 是基础设施）。在 `nodes` 表存 `key_hash`（沿用 `api_key_store._hash`），提供 `resolve_node_key(plaintext) -> node` 解析器。避免把 node 硬塞进 user 模型。备选（api_keys 加 node scope）记此但不取，理由：node 鉴权与 user 授权语义不同，分表更清晰。

3. **placement 独立表，PK=agent_id 强制 1:1**：不把 `node_id` 加到 `agents`（保持定义表纯净，placement 是运营态）。`agent_placements(agent_id PK→agents.id CASCADE, node_id→nodes.id RESTRICT, pinned_at, pinned_by, updated_at)`。PK(agent_id) 天然保证一 agent 至多一 placement。

4. **FK 删除策略**：`agent_id` ON DELETE CASCADE（删 agent 顺带清 placement）；`node_id` **RESTRICT**（删 node 前必须先解除其上 agent 的 pin，显式安全，不静默使 agent 失去归属）。node 注销保护与此一致。

5. **`last_seen_at` 列在本 change 建好但留空**：心跳由 C2 的实际态上报写。C1 立 schema，C2 填值——避免 C2 再加迁移。

6. **migration 号不写死**：当前 head 095，apply 时取下一个可用序号（`096_*` 或当时 head+1），`down_revision` 指向当时 head。

## Risks / Trade-offs

- **node RESTRICT 带来运维摩擦**：删 node 必须先 unpin 全部 agent。这是刻意的安全取舍（避免静默孤儿），可接受。
- **TEXT node-id 由人指定**：拼写/重复风险靠唯一约束 + 登记时冲突拒绝兜住。
- **service key 仅登记时返回一次**：丢失需重新 mint（轮换接口可后加；v1 注销+重登记即可）。
- **placement 1:1 限制**：未来单 agent HA（双实例 leader 选举）会突破 1:1——届时改为带"期望实例数/角色"的 placement，属 roadmap，不影响 v1 模型。
