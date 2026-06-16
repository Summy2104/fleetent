## Context

C1（`agent-node-registry`）已 apply 落 main（迁移 096）：`nodes`(id TEXT PK, key_hash unique, labels, last_seen_at NULL…)、`agent_placements`(agent_id PK→agents CASCADE, node_id→nodes RESTRICT)；store API `node_store.{register_node,get_node,list_nodes,resolve_node_key,deregister_node}`、`placement_store.{pin_agent,unpin_agent,list_by_node,get_for_agent}`。

C2 在此之上立**承重契约**：node 主动拉分区期望态 + 上报实际态。platform 不反向伸手（边界铁律）。这是 status 第一次真生效的接线点。

## Goals / Non-Goals

**Goals:**
- `GET /nodes/{id}/desired-state`：node 鉴权 + 按 placement 分区 + 按 status=enabled 过滤 + 附非密配置载荷。
- `POST /nodes/{id}/status`：心跳刷 `last_seen_at` + 持久化 per-agent 实际态投影。
- node 自限：node 只能读/报自身。

**Non-Goals:**
- 不下发 secret（C4 扩展配置载荷）。
- 不做 node 侧消费/reconcile（C3）。
- 不拆 start/stop（C5）。
- 不 modify `agent-lifecycle-toggle`：status 行为不变、仅多一消费者 → 新行为全落新 capability。

## Decisions

1. **status 接线落在新 capability，不改既有**：enable/disable/archive 语义不变，desired-state 过滤是**新增消费**，按"新增不改既有"原则放 `node-desired-state-api`，不碰 `agent-lifecycle-toggle`/`platform-agent-lifecycle`（后者由 C5 动）。

2. **配置载荷复用 `materialize.agent_file_from_store`**：它已能从 store 产出 AgentFile（`write_home` 才落盘）。C2 取其产物**序列化进 API 响应**（不写本地盘），node 侧再写本地 home。可能新增一个"AgentFile→可下发 dict/yaml"的序列化 helper，不改 materialize 既有写盘路径。

3. **node 鉴权用 `resolve_node_key` + URL 自限**：复用 C1 解析器；额外校验 URL `{id}` == 解析出的 node-id，拒绝跨 node。鉴权依赖注入式接线（仿 server 既有 `_authenticate`/resolver 模式），便于测试 mock。

4. **per-agent 实际态需新表 `node_agent_status`**（本 change 唯一迁移）：C1 的 `nodes.last_seen_at` 够心跳，但"哪个 agent 在跑/pid/健康"是新数据。建 `node_agent_status(agent_id PK→agents.id CASCADE, node_id→nodes.id CASCADE, phase, pid, health, detail, reported_at)`。agent→node 1:1 故 agent_id 作 PK。**实际态是只读投影**（控制真相在 node PID 文件），platform 不据其做控制。

5. **迁移号不写死**：当前 head 096，apply 时取下一个（预期 097），`down_revision` 指当时 head；merge 后自检单 head。

## Risks / Trade-offs

- **配置载荷边界**：必须确保非密/密分离——C2 只下发非密，避免提前泄密；secret 留 C4。序列化 helper 要明确剔除任何 secret 字段。
- **实际态投影一致性**：node 上报可能滞后/丢失；`last_seen_at` 陈旧即视为 node 不健康（判定阈值属 config，本 change 存数据、判定展示可后续）。
- **`node_agent_status` 与 placement 的关系**：placement=期望(该 node 该有谁)，node_agent_status=实际(报上来谁在跑)。两者可能短暂不一致（reconcile 收敛中），这是预期，不强一致。
- **鉴权 seam**：与现有 platform bearer(`ma-` user key) 区分——node key 也是 `ma-` 前缀但解析走 `nodes` 表而非 `api_keys`，两条解析路径不可混淆（测试覆盖：user key 不能当 node key 用、反之亦然）。
