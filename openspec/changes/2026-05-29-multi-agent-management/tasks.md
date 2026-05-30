## 1. Schema 与基础数据访问

- [ ] 1.1 Write failing tests: `agent_versions` 表在 `_init_db()` 后存在；`agents` 表有 `active_version_id` / `deleted_at` 列；`users` 表有 `is_admin` 列；`channel_agents` 表有 `bound_version_id` 列；旧 schema 启动时自动 ALTER 不丢数据
- [ ] 1.2 修改 `agent_store._init_db()` / `user_store._init_db()`：建新表、给老表加列（用 `PRAGMA table_info` 检测幂等添加）
- [ ] 1.3 Write failing tests: `create_agent(name, system_prompt, allowed_tools, *, skills_dir=None, mcp_server_ids=None, model_overrides=None, memory_namespace="default")` 同时插入 agents + agent_versions(version=1)，`active_version_id` 指向新行；同名非软删 agent 抛 `ValueError`
- [ ] 1.4 重写 `agent_store.create_agent`：用 `BEGIN/COMMIT` 单事务两表写入，返回 `Agent` dataclass（保留旧字段语义）
- [ ] 1.5 Write failing tests: `create_version(name, **partial_fields)` 拷贝当前 active 版本的字段，按 partial 覆盖，写入 `version = max(version)+1`，默认更新 `active_version_id`；`activate=False` 时保留旧 active
- [ ] 1.6 实现 `agent_store.create_version`、`activate_version(name, version)`、`list_versions(name)`、`soft_delete(name)`、`get_by_name_version(name, version)`

## 2. agent_runtime — AgentSnapshot 与解析器

- [ ] 2.1 Write failing tests: `AgentSnapshot` 是 frozen dataclass；`load_active(name)` 解包 agents + agent_versions 返回完整 snapshot；不存在/已软删返回 `None`
- [ ] 2.2 新建 `agent_runtime.py`：定义 `AgentSnapshot`；实现 `load_active(name)`、`load_version(version_id)`、`load_version_by_name(name, version)`
- [ ] 2.3 Write failing tests: `resolve_agent_for_request(platform, channel_id, user_id)` 严格按 channel > user > default_agent_name 顺序返回 snapshot
- [ ] 2.4 实现 `agent_runtime.resolve_agent_for_request`；替换 `normalizer.get_agent_for_context` 内部调用为 `agent_runtime.resolve_agent_for_request`（保留旧函数签名兼容）

## 3. Per-agent skills 隔离

- [ ] 3.1 Write failing tests: `SkillIndex(skills_dir)` 实例 scan 后只见到该目录下 SKILL.md；不污染模块级 `_index`；`match` / `load` 走实例数据
- [ ] 3.2 在 `skill_registry.py` 新增 `SkillIndex` 类，重构模块级函数复用 `SkillIndex(DEFAULT_DIR)`；保留旧 `scan/match/load/list_skills` 签名
- [ ] 3.3 Write failing tests: 当 `snapshot.skills_dir` 非空时,`agent_loop.run_stream` 命中 skill 走该目录下的 SKILL.md（不污染全局 index）；为空时走全局 `match`/`load`
- [ ] 3.4 修改 `agent_loop.run` / `run_stream` / `run_sync`：根据 `snapshot.skills_dir` 选择 `SkillIndex` 实例 vs 全局函数

## 4. Per-agent MCP server 白名单与 allowed_tools 双重过滤

- [ ] 4.1 Write failing tests: 当 `mcp_server_ids=["github"]`，`get_schemas()` 过滤后保留 `github__*`，排除 `gitlab__*`；当 `mcp_server_ids=[]` 排除所有 `*__*`（含 `__` 的 MCP 工具命名）
- [ ] 4.2 在 `agent_runtime.py` 新增 `filter_tool_schemas(schemas, allowed_tools, mcp_server_ids) -> list`（先按 allowed_tools fnmatch，再按 mcp 白名单前缀过滤）
- [ ] 4.3 修改 `agent_loop.run` / `run_stream`：接受 `snapshot: AgentSnapshot | None`，存在时用 `filter_tool_schemas` 替代当前过滤；旧 `allowed_tools` 参数保留作为 fallback

## 5. Per-agent 模型路由 overrides

- [ ] 5.1 前置确认：`RouteConfig` 已是 `@dataclass(frozen=True)`（见 `model_router.py`，无需改造）；若审阅后该前提变化需在本步处理
- [ ] 5.2 Write failing tests: `get_async_client_and_config("default", overrides={"default":{"model":"x"}})` 返回 `model="x"` 其它字段同 ROUTES；overrides 不含 task_type 时不影响；`get_client_and_config` 同步版本同行为
- [ ] 5.3 修改 `model_router.py`：两个函数都加 `overrides: dict | None = None`，用 `dataclasses.replace` 合并
- [ ] 5.4 修改 `agent_loop.run` / `run_stream` / `memory_layer.extract_and_save`：调用处下传 `snapshot.model_overrides`

## 6. Per-agent memory namespace

- [ ] 6.1 Write failing tests: `_mem_path(user_id, namespace)` 返回 `data/users/{user_id}/memories/{namespace}.jsonl`；`load_memories(user_id, namespace="x")` 只读对应文件；`extract_and_save(..., namespace="x")` 只写对应文件
- [ ] 6.2 修改 `memory_layer`：`_mem_path` 加 namespace 参数（默认 `"default"`），新增 `MEMORIES_ROOT = Path("data/users")` 模块常量供 monkeypatch
- [ ] 6.3 修改所有调用点（`agent_loop.run`、`run_stream`、`run_sync`）：从 snapshot.memory_namespace 取值传入
- [ ] 6.4 Write failing tests: migration 脚本把 `data/users/u1/memories.jsonl` 移到 `data/users/u1/memories/default.jsonl`；目标已存在时不覆盖；幂等运行
- [ ] 6.5 新建 `scripts/migrate_memories_to_namespace.py`

## 7. Session 版本锁定

- [ ] 7.1 Write failing tests: `session_mgr.load(session_id)` 对老格式（顶层列表）和新格式（`{meta, messages}`）都返回 `messages`；`load_meta(session_id)` 返回 meta dict 或空 dict；`save(session_id, messages, meta=None)` 写入新格式
- [ ] 7.2 重构 `session_mgr` 内部存储为 `{"meta": {...}, "messages": [...]}`；读时兼容老格式自动转换；保留 `load(session_id) -> list` 签名向后兼容，新增 `load_meta`
- [ ] 7.3 Write failing tests: session 第一次写入时 meta 中持久化 `agent_id` 和 `agent_version_id`；后续在同 session 中 activate 不同 version 不影响该 session 解析；新 session 拿当前 active
- [ ] 7.4 修改 `normalizer.route` 与 `/chat`：从 session meta 优先解析 snapshot，否则按 resolve_agent_for_request 解析并写回 meta

## 8. invoke_agent 工具

- [ ] 8.1 Write failing tests: `invoke_agent(agent_name, message)` 对存在的 agent 返回其 reply 字符串；对不存在的 agent 返回 `agent {name!r} not found`；被调 agent 视图中 `invoke_agent` / `sub_agent` 均不可见
- [ ] 8.2 在 `tools.py` 添加 `invoke_agent` 工具（`risk_level="medium"`）；内部用 `agent_runtime.load_active` + `agent_loop.run(..., is_sub_agent=True, snapshot=...)`
- [ ] 8.3 修改 `agent_loop.run` 工具 schema 排除清单：`is_sub_agent=True` 时同时排除 `sub_agent` 和 `invoke_agent`

## 9. is_admin 标志与认证守卫

- [ ] 9.1 Write failing tests: `users` 表新建后 `is_admin` 默认 0；`promote_admin(user_id)` / `revoke_admin(user_id)` 切换该列；`get_by_api_key(api_key)` 返回的 `User` 含 `is_admin` 属性
- [ ] 9.2 修改 `user_store`：加 `is_admin` 列；新增 `promote_admin` / `revoke_admin`；`User` dataclass 加 `is_admin` 字段
- [ ] 9.3 Write failing tests: `_require_admin` 依赖在 `is_admin=0` 时抛 403；`is_admin=1` 时返回 user_id
- [ ] 9.4 在 `server.py` 新增 `_require_admin = Depends(...)` 守卫

## 10. agent_admin_api — FastAPI 路由

- [ ] 10.1 Write failing tests: `POST /admin/agents` 用 admin token 201、用普通 token 403、重名 409；body 缺字段 422；`GET /admin/agents/{name}` 不存在或软删返回 404；`DELETE /admin/agents/{name}` 204 后再 GET 返回 404
- [ ] 10.2 新建 `agent_admin_api.py`：FastAPI APIRouter；实现 `POST/GET/PATCH/DELETE /admin/agents` 与 `GET /admin/agents/{name}`
- [ ] 10.3 Write failing tests: `GET /admin/agents/{name}/versions` 返回按 version desc 的列表，含 `is_active` 字段；`POST /admin/agents/{name}/versions/{v}/activate` 切换 active_version_id；不存在的 version → 404
- [ ] 10.4 实现版本相关三个 endpoint
- [ ] 10.5 Write failing tests: bindings 四个 endpoint（POST/DELETE users、POST/DELETE channels）含权限校验和正确数据库副作用；POST channel 同时写入 `bound_version_id`
- [ ] 10.6 实现 bindings 四个 endpoint
- [ ] 10.7 在 `server.py` lifespan 中 `app.include_router(agent_admin_router)`

## 11. CLI 新命令

- [ ] 11.1 Write failing tests: `update-agent` 创建新版本并默认激活；`list-agent-versions` 输出每个版本的 id/version/is_active/created_at；`activate-agent-version --version N` 切换；不存在的 version exit 非零
- [ ] 11.2 在 `admin.py` 添加 `update-agent` / `list-agent-versions` / `activate-agent-version` / `show-agent` / `delete-agent` 命令
- [ ] 11.3 Write failing tests: `assign-user` / `unassign-user` 操作 user_agents 表；`promote-admin` / `revoke-admin` 切换 is_admin
- [ ] 11.4 在 `admin.py` 添加 `assign-user` / `unassign-user` / `promote-admin` / `revoke-admin` 命令

## 12. 现有 agent 数据迁移（启动期一次）

- [ ] 12.1 Write failing tests: 升级时若 agents 表中存在无 active_version_id 的行，启动后这些行自动获得 version=1（mirror system_prompt/allowed_tools），`mcp_server_ids` 设为当前所有已注册 server id（行为兼容），`memory_namespace='default'`，并填好 active_version_id
- [ ] 12.2 在 `agent_store._init_db()` 末尾加幂等 `_backfill_v1_versions()` 函数

## 13. 验证

- [ ] 13.1 运行完整测试套件 (`uv run pytest -x -q`)，确认全部通过
- [ ] 13.2 `uv run ruff check src tests && uv run ruff format src tests`
- [ ] 13.3 `uv run mypy src` 通过
- [ ] 13.4 手动验证：
  - `create-user` + `promote-admin` → 用该 token 调 `POST /admin/agents` 创建 agent → `PATCH` 创建 v2 → `GET /admin/agents/x/versions` 看到两个版本 → `POST .../v1/activate` 回滚 → 期间发起的 SSE `/chat` session 不被打断
  - 手动跑 `scripts/migrate_memories_to_namespace.py` 在一个含旧文件的 fixture 目录上
- [ ] 13.5 自检：所有新 task 的实现 task 前都有对应 failing-test task；spec deltas 与 tasks 对得上；无新 AI 框架/ORM/云专有服务依赖
