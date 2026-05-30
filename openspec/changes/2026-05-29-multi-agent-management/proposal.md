## Why

平台已有基础多 agent 支持（`agent_store` 的 agents / user_agents / channel_agents 三张表 + admin CLI 的 channel 绑定 + `default_agent_name` 全局默认值），但**只能"定义一次、用一辈子"**：

1. **管理面只有 CLI**：没有 HTTP API，运维要 ssh 进容器；外部系统（控制台、CI）无法接入。
2. **没有版本化**：改 system_prompt 直接覆盖，无法回滚；运行中的 session 会在下一轮发现 prompt 突变。
3. **资源没隔离**：所有 agent 共享同一份 skills 目录、同一组 MCP servers、同一份 memories.jsonl、同一个 default route。多租户场景下"客服 agent"能看到"运维 agent"的记忆和工具。
4. **agent 间无法显式协作**：`sub_agent` 工具只能 spawn 匿名 anonymous worker 跑同一份配置；没法说"把这个交给 `analyst` agent"。

这是阻塞平台走向多团队/多业务线部署的关键缺口。

## What Changes

新增以下能力（按 capability 拆分，便于增量验收）：

**ADDED**
- `agent-versioning`：`agent_versions` 表保存每次 PATCH 的完整快照（system_prompt、allowed_tools、skills_dir、mcp_server_ids、model_overrides、memory_namespace）；`agents.active_version_id` 指向当前生效版本。
- `agent-admin-api`：FastAPI `/admin/agents/*` 路由集——agent CRUD、版本列表、激活/回滚、user / channel 绑定。复用 Bearer 认证 + 新增 `users.is_admin` 标志位。
- `agent-resource-isolation`：每个 agent version 可独立指定 skills 目录、MCP server 白名单、模型路由覆盖、memory namespace；所有路径常量保留 monkeypatch 可注入特性。
- `agent-invocation`：内置 `invoke_agent(agent_name, message)` 工具（risk_level="medium"），按目标 agent 当前 active version 加载快照运行，沿用 sub_agent 深度限制 1。

**MODIFIED**
- `agent-definition`：`Agent` 数据类加 `active_version_id` / `deleted_at`；`get_by_name` 默认返回 active version 解包后的完整定义；新增 `get_by_name_version(name, version)`、`soft_delete(name)`、`assign_user` 已有但 admin CLI 新增 `assign-user` / `unassign-user` 命令。
- `channel-agent-binding`：绑定时记录"绑定时刻的 active_version_id"作为审计字段（不锁定版本——channel 仍跟随 active）。

**会话快照锁定**：session 创建时记录 `(agent_id, agent_version_id)`，session 整个生命周期内使用该版本；session 结束（或被显式清空）后，新 session 拿当前 active。具体实现见 design.md。

## Capabilities

### New Capabilities

- `agent-versioning`
- `agent-admin-api`
- `agent-resource-isolation`
- `agent-invocation`

### Modified Capabilities

- `agent-definition`
- `channel-agent-binding`

## Impact

- **代码**：
  - 新增：`agent_admin_api.py`（FastAPI router）、`agent_runtime.py`（version snapshot + isolation resolver）
  - 修改：`agent_store.py`（多 schema + 版本 API）、`server.py`（mount admin router）、`admin.py`（CLI 新命令）、`agent_loop.py`（接受 AgentSnapshot）、`skill_registry.py`（支持非全局 dir）、`memory_layer.py`（支持 namespace 后缀）、`model_router.py`（支持 per-call overrides）、`session_mgr.py`（持久化 agent_version_id）、`user_store.py`（is_admin 列）
- **依赖**：无新增依赖（FastAPI、APScheduler、aiosqlite 已在）。
- **数据**：`data/users.db` 新增 `agent_versions` 表，`agents` 加 `active_version_id` / `deleted_at` 列，`users` 加 `is_admin` 列，`channel_agents` 加 `bound_version_id` 列（审计）。memories 路径变成 `data/users/{user_id}/memories/{namespace}.jsonl`，旧文件通过 migration 步骤迁移到 `default` namespace。
- **破坏性**：
  - `Agent` 数据类字段扩展，原 `system_prompt` / `allowed_tools` 仍存在并继续可用（从 active version 解包）。
  - memories 文件路径变化——需 migration 脚本（一次性把 `memories.jsonl` 移到 `memories/default.jsonl`）。
  - 现有外部脚本若直接读 `agents.system_prompt` 列将得到 NULL；该列保留但置空，应改读 `agent_versions`。

## Commit 切分建议

按 capability 拆，每个 commit 自包含可单独 review：

1. `feat(agent_store): add agent_versions table and backfill v1`（schema + 数据迁移，含 12.x）
2. `feat(agent_runtime): introduce AgentSnapshot and resolver`（2.x）
3. `refactor(skill_registry): support per-agent SkillIndex`（3.x）
4. `feat(agent_loop): apply mcp_server_ids and skills_dir from snapshot`（4.x）
5. `feat(model_router): per-call route overrides`（5.x）
6. `feat(memory_layer): per-agent memory namespace + migration script`（6.x）
7. `feat(session_mgr): persist agent_version_id in session meta`（7.x）
8. `feat(tools): invoke_agent built-in tool`（8.x）
9. `feat(user_store): is_admin flag and admin guard`（9.x）
10. `feat(server): /admin/agents REST API`（10.x）
11. `feat(admin): CLI commands for agent version, bindings, admin role`（11.x）

每个 commit 内部仍按 TDD：测试先红 → 实现 → 绿。
