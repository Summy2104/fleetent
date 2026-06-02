> **重写说明（2026-06-02）**：本 tasks 已按现架构重写——schema 走 Alembic（不在 store `_init_db` 里 ALTER）、认证走 role 体系 + Session（删除原 is_admin section）、HTTP 管理面复用现有 `/admin/agents`（agent_console_api + agent_apply_api）只新增版本/绑定端点。每个实现 task 前有对应 failing-test task。

## 1. Schema 迁移（Alembic）

- [ ] 1.1 Write failing tests: 迁移 upgrade 后 `agent_versions` 表存在（列 id / agent_id / version / system_prompt / allowed_tools / skills_dir / mcp_server_ids / model_overrides / memory_namespace / created_at）；`agents` 表有 `active_version_id` 列；`channel_agents` 表有 `bound_version_id` 列；downgrade 干净回滚
- [ ] 1.2 新建 Alembic 迁移 `026_add_agent_versions`（基于最新 revision 025）：建表 + 加列；named params 风格；不复制 store `_init_db` 建表
- [ ] 1.3 Write failing tests: 存量 `agents` 行（无 active_version_id）在 backfill 后获得 version=1（mirror system_prompt/allowed_tools，mcp_server_ids=NULL 表示"全部"，memory_namespace='default'），active_version_id 填好；幂等重跑不重复建版本
- [ ] 1.4 在迁移中实现幂等 `_backfill_v1_versions()`（data migration 段），对存量行补 v1

## 2. agent_store — 版本数据访问

- [ ] 2.1 Write failing tests: `create_agent(name, system_prompt, allowed_tools, *, skills_dir=None, mcp_server_ids=None, model_overrides=None, memory_namespace="default")` 单事务插入 agents + agent_versions(version=1) 并设 active_version_id；同名 agent 抛 `ValueError`；返回的 `Agent` 含 `active_version_id`
- [ ] 2.2 重写 `agent_store.create_agent`（保留旧字段语义）；`Agent` dataclass 加 `active_version_id`
- [ ] 2.3 Write failing tests: `create_version(name, **partial)` 拷贝当前 active 版本字段、按 partial 覆盖、`version=max+1`，默认更新 active_version_id；`activate=False` 保留旧 active；`activate_version(name, v)`、`list_versions(name)`（version desc + is_active）、`get_by_name_version(name, v)` 行为
- [ ] 2.4 实现 `create_version` / `activate_version` / `list_versions` / `get_by_name_version`
- [ ] 2.5 Write failing tests: `get_by_name(name)` 返回的 system_prompt / allowed_tools 来自 active version（改 version 后随之变化）
- [ ] 2.6 调整 `get_by_name` 从 active version 解包字段（向后兼容签名与返回类型）

## 3. agent_runtime — AgentSnapshot 与解析器

- [ ] 3.1 Write failing tests: `AgentSnapshot` 是 frozen dataclass（字段含 agent_id/name/version/system_prompt/allowed_tools/skills_dir/mcp_server_ids/model_overrides/memory_namespace）；`load_active(name)` 解包返回 snapshot；不存在返回 `None`；`load_version_by_name(name, v)` 取指定版本
- [ ] 3.2 新建 `agent_runtime.py`：定义 `AgentSnapshot`；实现 `load_active` / `load_version` / `load_version_by_name`
- [ ] 3.3 Write failing tests: `resolve_agent_for_request(platform, channel_id, user_id)` 严格按 channel > user > default_agent_name 顺序返回 snapshot；都未命中返回 None
- [ ] 3.4 实现 `resolve_agent_for_request`（内部复用 agent_store 的 channel/user/default 解析）

## 4. Per-agent skills 隔离

- [ ] 4.1 Write failing tests: `SkillIndex(skills_dir)` 实例 scan 后只见该目录 SKILL.md；不污染模块级 `_index`；`match`/`load` 走实例数据
- [ ] 4.2 在 `skill_registry.py` 新增 `SkillIndex` 类，重构模块级函数复用 `SkillIndex(默认目录)`；保留旧 `scan/match/load/list_skills` 签名

## 5. Per-agent MCP 白名单 + allowed_tools 双重过滤

- [ ] 5.1 Write failing tests: `filter_tool_schemas(schemas, allowed_tools, mcp_server_ids)`：先按 allowed_tools fnmatch，再按 mcp 白名单前缀；`mcp_server_ids=["github"]` 保留 `github__*` 排除 `gitlab__*`；`mcp_server_ids=[]` 排除所有含 `__` 的工具；`mcp_server_ids=None` 不按 mcp 过滤
- [ ] 5.2 在 `agent_runtime.py` 实现 `filter_tool_schemas`

## 6. Per-agent 模型路由 overrides

- [ ] 6.1 前置确认：`RouteConfig` 已 `frozen=True`（model_router.py），无需改造
- [ ] 6.2 Write failing tests: `get_async_client_and_config("default", overrides={"default":{"model":"x"}})` 返回 `model="x"` 其它字段同 ROUTES；overrides 不含该 task_type 时不影响；`get_client_and_config` 同步版本同行为
- [ ] 6.3 修改 `model_router.py`：两函数加 `overrides: dict | None = None`，用 `dataclasses.replace` 合并

## 7. Per-agent memory namespace

- [ ] 7.1 Write failing tests: `_mem_path(user_id, namespace="default")` 返回 `data/users/{user_id}/memories/{namespace}.jsonl`；`load_memories(user_id, namespace="x")` 只读对应文件；`extract_and_save(..., namespace="x")` 只写对应文件
- [ ] 7.2 修改 `memory_layer`：`_mem_path` 加 namespace（默认 default），加 `MEMORIES_ROOT` 模块常量供 monkeypatch
- [ ] 7.3 Write failing tests: 幂等迁移把 `data/users/u1/memories.jsonl` 移到 `memories/default.jsonl`；目标已存在不覆盖；重跑幂等
- [ ] 7.4 新建 `scripts/migrate_memories_to_namespace.py`（或 memory_layer 内幂等函数）

## 8. Session 版本锁定

- [ ] 8.1 Write failing tests: `load(session_id)` 对老格式（顶层列表）和新格式（`{meta, messages}`）都返回 messages；`load_meta(session_id)` 返回 meta dict 或 `{}`；`save(session_id, messages, meta=None)` 写新格式
- [ ] 8.2 重构 `session_mgr` 内部存储为 `{meta, messages}`；读时兼容老格式；保留 `load -> list` 签名；新增 `load_meta`
- [ ] 8.3 Write failing tests: session 首写时 meta 持久化 `agent_id` + `agent_version_id`；之后 activate 不同 version 不影响该 session；新 session 拿当前 active

## 9. agent_loop 应用 snapshot

- [ ] 9.1 Write failing tests: `run`/`run_stream` 接受 `snapshot: AgentSnapshot | None`，存在时：skills 走 `snapshot.skills_dir`、工具走 `filter_tool_schemas`、模型走 `snapshot.model_overrides`、memory 走 `snapshot.memory_namespace`；为空时维持当前全局行为
- [ ] 9.2 修改 `agent_loop.run` / `run_stream` / `run_sync` 接受并应用 snapshot（旧 `allowed_tools` / `agent_name` 参数保留为 fallback）
- [ ] 9.3 修改 `normalizer.route` 与 `/chat`：优先从 session meta 解析 snapshot，否则 `resolve_agent_for_request` 解析并写回 meta

## 10. invoke_agent 工具

- [ ] 10.1 Write failing tests: `invoke_agent(agent_name, message)` 对存在 agent 返回 reply 字符串；对不存在返回 `agent {name!r} not found`；被调 agent 视图中 `invoke_agent`/`sub_agent` 不可见
- [ ] 10.2 在 `tools.py` 添加 `invoke_agent`（risk medium）：内部 `agent_runtime.load_active` + `agent_loop.run(..., is_sub_agent=True, snapshot=...)`
- [ ] 10.3 修改 `agent_loop` 工具排除：`is_sub_agent=True` 时排除 `sub_agent` 和 `invoke_agent`

## 11. agent_admin_api — 版本与绑定 REST

- [ ] 11.1 Write failing tests: `GET /admin/agents/{name}/versions` admin/viewer 可读返回 version desc 列表含 `is_active`；未认证 401；`POST /admin/agents/{name}/versions/{v}/activate` admin 切换 active、viewer 403、不存在 version 404
- [ ] 11.2 新建 `agent_admin_api.py`（Session 认证 + role guard，复用 `_current_user`/`_is_admin` 模式）：实现 versions list + activate 端点
- [ ] 11.3 Write failing tests: bindings 四端点（POST/DELETE user、POST/DELETE channel）权限校验 + 数据库副作用；POST channel 同时写 `bound_version_id`
- [ ] 11.4 实现 bindings 四端点
- [ ] 11.5 在 `server.py` mount `agent_admin_api.router`

## 12. CLI 新命令

- [ ] 12.1 Write failing tests: `update-agent` 创建新版本并默认激活；`list-agent-versions` 输出 id/version/is_active/created_at；`activate-agent-version --version N` 切换；不存在 version 非零退出
- [ ] 12.2 在 admin CLI 添加 `update-agent` / `list-agent-versions` / `activate-agent-version` / `show-agent`
- [ ] 12.3 Write failing tests: `assign-user` / `unassign-user` 操作 user_agents 表
- [ ] 12.4 在 admin CLI 添加 `assign-user` / `unassign-user`

## 13. 验证

- [ ] 13.1 `uv run pytest -x -q` 全绿
- [ ] 13.2 `uv run ruff format src tests && uv run ruff check src tests`
- [ ] 13.3 `uv run mypy src` 通过
- [ ] 13.4 手动验证：create-user + set-role admin → Session 登录 → `POST /admin/agents/apply` 建 agent → CLI `update-agent` 建 v2 → `GET /admin/agents/x/versions` 两版本 → `POST .../1/activate` 回滚 → 期间 SSE `/chat` session 不被打断；跑 memories 迁移在含旧文件的 fixture 上
- [ ] 13.5 自检：实现 task 前都有 failing-test task；spec deltas 与 tasks 对得上；无新 AI 框架 / ORM / 云专有依赖；schema 走 Alembic；认证走 role 体系
