## Why

平台已有基础多 agent 支持，且管理面已在近期演进：

- `agent_store` 三张表（agents / user_agents / channel_agents）+ admin CLI channel 绑定 + `default_agent_name` 全局默认值。
- `agent_admin_store`（agent_admin_state 侧表：status / provenance / drift / archived_at）+ `agent_console_api`（`/admin/agents` 生命周期：list / enable / disable / archive / restore / clone / observability）+ `agent_apply_api`（`/admin/agents/apply`、`apply:batch`）。
- 认证已从 `is_admin` 布尔位演进为 **role 体系**：`user_store.role`（viewer / admin / built_in_admin）+ `auth.has_role` + Session 认证（`Authorization: Session <token>`）。

但仍**只能"定义一次、用一辈子"**，三个缺口阻塞多团队/多业务线部署：

1. **没有版本化**：改 system_prompt 直接覆盖 `agents` 行，无法回滚；运行中的 session 会在下一轮发现 prompt 突变。
2. **资源没隔离**：所有 agent 共享同一份 skills 目录、同一组 MCP servers、同一份 memories、同一个 default route。多租户下"客服 agent"能看到"运维 agent"的记忆和工具。
3. **agent 间无法显式协作**：`sub_agent` 只能 spawn 匿名 worker 跑同一份配置；没法"把这个交给 `analyst` agent"。

## What Changes

按 capability 拆分，便于增量验收。**与现架构对齐的关键修订**：认证一律走现有 **role 体系 + Session 认证**（不再引入 `users.is_admin`）；HTTP 管理面**复用**现有 `/admin/agents` 表面，只新增版本与绑定端点，不重复 apply/lifecycle。

**ADDED**

- `agent-versioning`：新增 `agent_versions` 表（Alembic 迁移），保存每次更新的完整快照（system_prompt、allowed_tools、skills_dir、mcp_server_ids、model_overrides、memory_namespace）；`agents.active_version_id` 指向当前生效版本。`create_agent` 写入 v1；`create_version` / `activate_version` / `list_versions` / `get_by_name_version`。启动期幂等 backfill 把存量 agent 补成 v1。
- `agent-resource-isolation`：每个 version 可独立指定 skills 目录、MCP server 白名单、模型路由覆盖、memory namespace。`agent_runtime.AgentSnapshot` 解包 active version；`agent_loop` 接受 snapshot；`skill_registry.SkillIndex` 支持非全局目录；`filter_tool_schemas` 双重过滤（allowed_tools fnmatch + mcp 白名单前缀）；`model_router` 加 `overrides`；`memory_layer` 加 namespace。所有路径常量保留 monkeypatch 可注入。
- `agent-invocation`：内置 `invoke_agent(agent_name, message)` 工具（`risk_level="medium"`），按目标 agent 当前 active version 加载快照运行，沿用 sub_agent 深度限制 1；被调 agent 视图中 `invoke_agent` / `sub_agent` 均不可见。
- `agent-admin-api`：在现有 `/admin/agents` 路由集上**新增**版本端点（list versions、activate version）与绑定端点（user / channel assign / unassign），鉴权复用 `_current_user` + role guard（admin 写、viewer 读），与 `agent_console_api` / `agent_apply_api` 共存不重复。

**MODIFIED**

- `agent-definition`：`Agent` 数据类加 `active_version_id`；`get_by_name` 仍返回完整定义（system_prompt / allowed_tools 从 active version 解包，向后兼容旧字段语义）；新增 `get_by_name_version(name, version)`。**不引入 `deleted_at`**——软删/归档复用现有 `agent_admin_store.archive`。
- `channel-agent-binding`：绑定时记录"绑定时刻的 active_version_id"作为审计字段 `bound_version_id`（不锁定版本——channel 仍跟随 active）。

**会话快照锁定**（归入 agent-versioning）：session 首次写入时在 meta 中持久化 `(agent_id, agent_version_id)`，session 整个生命周期内使用该版本；session 结束后新 session 拿当前 active。`session_mgr` 存储升级为 `{meta, messages}`，读时兼容旧顶层列表格式。

## Capabilities

### New Capabilities

- `agent-versioning`
- `agent-resource-isolation`
- `agent-invocation`
- `agent-admin-api`

### Modified Capabilities

- `agent-definition`
- `channel-agent-binding`

## Impact

- **代码**：
  - 新增：`agent_runtime.py`（AgentSnapshot + resolver + filter_tool_schemas）、`agent_admin_api.py`（versions + bindings 路由）。
  - 修改：`agent_store.py`（agent_versions API + active_version_id）、`skill_registry.py`（SkillIndex 类）、`model_router.py`（overrides 参数）、`memory_layer.py`（namespace 参数）、`session_mgr.py`（meta/messages 格式）、`agent_loop.py`（接受 snapshot）、`tools.py`（invoke_agent）、`normalizer.py`（snapshot 解析 + 写回 meta）、`server.py`（mount router）、admin CLI（version / binding 命令）。
- **依赖**：无新增依赖（FastAPI、Alembic、aiosqlite 已在）。
- **数据**：Alembic 迁移新增 `agent_versions` 表，`agents` 加 `active_version_id` 列，`channel_agents` 加 `bound_version_id` 列。memories 路径变成 `data/users/{user_id}/memories/{namespace}.jsonl`，旧 `memories.jsonl` 幂等迁移到 `default` namespace。**`users` 表不变**。
- **破坏性**：
  - `Agent` 数据类加 `active_version_id` 字段；`system_prompt` / `allowed_tools` 继续可用（从 active version 解包）。
  - memories 文件路径变化——需幂等迁移（`memories.jsonl` → `memories/default.jsonl`）。
  - session 文件格式升级——`session_mgr.load` 保留 `-> list` 签名向后兼容，读时自动转换旧格式。

## Commit 切分建议

按 capability 拆，每个 commit 自包含可单独 review；内部仍按 TDD（红→绿）：

1. `feat(db-migration): add agent_versions table and active_version_id/bound_version_id columns`（schema，含 backfill）
2. `feat(agent_store): version API + create_agent writes v1`
3. `feat(agent_runtime): AgentSnapshot, resolver, filter_tool_schemas`
4. `refactor(skill_registry): SkillIndex for per-agent skills dir`
5. `feat(model_router): per-call route overrides`
6. `feat(memory_layer): per-agent memory namespace + migration`
7. `feat(session_mgr): meta/messages format with agent_version lock`
8. `feat(agent_loop): apply AgentSnapshot (skills/mcp/model/memory/tool filter)`
9. `feat(tools): invoke_agent built-in tool`
10. `feat(agent_admin_api): version + binding REST endpoints`
11. `feat(admin_cli): version + binding commands`
