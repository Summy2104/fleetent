## Context

现状回顾：

- `agent_store.Agent` 是扁平 dataclass：`id / name / system_prompt / allowed_tools`，单表覆盖定义。
- `agent_loop.run()` 直接接受 `system_prompt` 和 `allowed_tools` 参数；`server.py /chat` 在请求入口处通过 `get_agent_for_context()` 解析到 `Agent`，再展开传入。
- `skill_registry` 是模块级 `_index` 字典，`scan()` 全局替换，没法在同一 server 里同时维护多套 skills 索引。
- `memory_layer._mem_path(user_id)` 写到 `data/users/{user_id}/memories.jsonl`，全 agent 共享。
- `model_router.ROUTES` 是模块级常量，没有 per-call override 入口。
- `mcp_client._server_registry` 是全局的，所有 server 都注册到 `tool_registry`，agent 隔离只能靠 `allowed_tools` 白名单（glob）。
- `user_store.users` 表无 admin 标志位。

设计原则：**不破坏现有接口契约**——`agent_loop.run()` 的位置参数（system_prompt / allowed_tools）继续可用，新功能通过追加一个 `AgentSnapshot | None` 可选参数承载。

## Goals / Non-Goals

**Goals**

- agent 定义可版本化、可回滚，运行中 session 不中断（snapshot 锁定到 session）。
- agent 全生命周期可通过 HTTP API 管理；CLI 保留并新增对等命令。
- 每个 agent 独立的 skills 目录、MCP server 白名单、模型路由覆盖、memory namespace。
- agent 间通过 `invoke_agent` 工具显式协作，最大调用深度 1（与 sub_agent 对齐）。
- 所有新增模块遵循 monkeypatch 可注入约定，测试用 `tmp_path` 完全隔离。

**Non-Goals**

- 不做"按规则自动路由"——agent 间路由由 agent 自己通过工具调用决定，不引入声明式路由 DSL。
- 不做 agent 配置的"GitOps"——agent 定义只在 SQLite，YAML 导入留到后续。
- 不做"灰度发布 / A-B"——版本切换是一次性原子操作。
- admin HTTP API 不提供 UI，纯 REST + JSON。
- 不引入 RBAC 三态权限模型，只一个二态 `is_admin` 标志位足够当前需求。

## Decisions

### 1. Schema：双表 + 软删除 + per-version 完整快照

```sql
-- 扩展原有 agents 表（不删字段，保兼容）
ALTER TABLE agents ADD COLUMN active_version_id INTEGER REFERENCES agent_versions(id);
ALTER TABLE agents ADD COLUMN deleted_at TEXT;
-- system_prompt / allowed_tools 列保留但 NULL（active version 提供真实值）

CREATE TABLE agent_versions (
    id                  INTEGER PRIMARY KEY,
    agent_id            INTEGER NOT NULL REFERENCES agents(id),
    version             INTEGER NOT NULL,           -- 单调递增，per agent_id
    system_prompt       TEXT NOT NULL,
    allowed_tools       TEXT NOT NULL,              -- JSON array
    skills_dir          TEXT,                       -- NULL → 用全局 default
    mcp_server_ids      TEXT NOT NULL DEFAULT '[]', -- JSON array
    model_overrides     TEXT NOT NULL DEFAULT '{}', -- JSON: {"default": {...}, "memory_extraction": {...}}
    memory_namespace    TEXT NOT NULL DEFAULT 'default',
    created_at          TEXT NOT NULL,
    created_by_user_id  TEXT,                       -- 谁创建的版本（HTTP API 时为 admin user）
    UNIQUE(agent_id, version)
);

ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0;
ALTER TABLE channel_agents ADD COLUMN bound_version_id INTEGER REFERENCES agent_versions(id);
```

**为什么不在 agents 行内 JSON 直接存历史**：版本越多查询越慢，外键约束/审计/UI 列表都更难写；SQLite 多表 join 廉价，分表是最朴素的选择。

### 2. AgentSnapshot — 运行期统一表示

新建 `agent_runtime.py`，定义不可变 dataclass：

```python
@dataclass(frozen=True)
class AgentSnapshot:
    agent_id: int
    agent_name: str
    version: int
    version_id: int
    system_prompt: str
    allowed_tools: list[str]
    skills_dir: str | None
    mcp_server_ids: list[str]
    model_overrides: dict[str, dict[str, Any]]
    memory_namespace: str
```

`resolve_agent_for_request(platform, channel_id, user_id) -> AgentSnapshot | None` 沿用现有 `default-agent` capability 的优先级（channel > user > default），但返回 snapshot 而非 `Agent`。

`agent_loop.run()` 新增可选参数 `snapshot: AgentSnapshot | None = None`；当传入时优先生效，覆盖旧的 `system_prompt` / `allowed_tools` / `agent_name`。

### 3. Session 版本锁定

`session_mgr` 当前只存 messages 列表。改为每个 session JSON 文件第一条隐式记录 `{"_meta": {"agent_id": ..., "version_id": ...}}`，或更稳的：拆 `data/sessions/{session_id}.json` → `{"meta": {...}, "messages": [...]}` 两段。

读取流程：
1. 入口处先 `session_mgr.load(session_id)` 得到 meta。
2. 若 meta.version_id 存在 → 直接 `agent_runtime.load_version(version_id)` 得到 snapshot；
3. 否则解析当前 active version 并写回 meta。

这样 PATCH 切换 active 不影响已有 session；新 session 才看到新版本。

session 结束后元数据保留，但若 admin 显式 `truncate-session` 或新对话则按上述流程重新解析。

### 4. Per-agent skills：把 skill_registry 改成实例化

`skill_registry` 当前是模块级单例。改造：

- 保留 `scan()` / `match()` / `load()` / `list_skills()` 模块级 API（默认 dir 来自 env），向后兼容。
- 新增 `SkillIndex` 类：构造时接收 `skills_dir`，内部维护私有 `_index`。`SkillIndex.match(text)` / `.load(name)`。
- `agent_loop.run_stream` 取 snapshot.skills_dir，命中时构造 `SkillIndex(snapshot.skills_dir)`；未命中则用全局 `scan()`/`match()`/`load()`。
- 模块级 `_index` 在 lifespan startup 时仍然 scan 默认目录，零配置时行为不变。

### 5. Per-agent MCP servers：白名单 + tool schema 过滤

MCP 仍全局注册（启动期连接昂贵，重复连接不必要）。在 `agent_loop.run()` 取 snapshot 后构造 effective allowlist：

```python
effective_allowed = list(snapshot.allowed_tools)
for server_id in snapshot.mcp_server_ids:
    effective_allowed.append(f"{server_id}__*")
# 若 snapshot.mcp_server_ids = []，不追加 MCP 工具
```

复用现有 `check_tool_access`（fnmatch）做最终过滤。意味着 agent 必须显式声明它能用哪些 MCP server——不在白名单里的 server 工具一律不可见。这一刻意收紧默认值是为多租户做铺垫。

### 6. Per-agent model overrides：route_overrides 参数

`model_router.get_async_client_and_config(task_type, overrides=None)` 新增 overrides 参数：

```python
def get_async_client_and_config(
    task_type: str = "default",
    overrides: dict[str, dict[str, Any]] | None = None,
) -> tuple[AsyncOpenAI, RouteConfig]:
    base = ROUTES.get(task_type, ROUTES["default"])
    if overrides and task_type in overrides:
        base = replace(base, **overrides[task_type])  # dataclasses.replace
    ...
```

调用方（`agent_loop.run`、`memory_layer.extract_and_save`）接受 snapshot.model_overrides 并下传。

### 7. Per-agent memory namespace

`memory_layer._mem_path(user_id, namespace='default')` → `data/users/{user_id}/memories/{namespace}.jsonl`。`load_memories` / `extract_and_save` 都接受 `namespace` 参数。

**Migration**：写一个一次性 `scripts/migrate_memories_to_namespace.py`，把 `data/users/*/memories.jsonl` 移到 `data/users/*/memories/default.jsonl`；幂等，已迁过的跳过。

### 8. invoke_agent 工具

新工具，risk_level="medium"（与 sub_agent 同等级，需要审批触发但非高风险）：

```python
@tool(
    name="invoke_agent",
    description="Invoke another agent by name and return its reply. ...",
    risk_level="medium",
)
async def invoke_agent(agent_name: str, message: str) -> str:
    snapshot = agent_runtime.load_active(agent_name)
    if snapshot is None:
        return f"agent {agent_name!r} not found"
    return await agent_loop.run(
        messages=[{"role": "user", "content": message}],
        is_sub_agent=True,           # 深度限制：被调 agent 不能再 invoke
        snapshot=snapshot,
    )
```

与 `sub_agent` 共用 `is_sub_agent` 标志，schema 里同样不暴露 `sub_agent` 和 `invoke_agent` 给子 agent，自然形成深度 1 上限。

### 9. HTTP Admin API：单独 router，强制 admin 校验

```
POST   /admin/agents                                    # 创建（同时建 version 1 并激活）
GET    /admin/agents                                    # 列出（含已删除可选 filter）
GET    /admin/agents/{name}                             # 当前 active 详情
PATCH  /admin/agents/{name}                             # 创建新版本（不激活）
GET    /admin/agents/{name}/versions                    # 版本列表
POST   /admin/agents/{name}/versions/{version}/activate # 激活（含回滚）
DELETE /admin/agents/{name}                             # 软删除

POST   /admin/agents/{name}/bindings/users              # body {user_id}
DELETE /admin/agents/{name}/bindings/users/{user_id}

POST   /admin/agents/{name}/bindings/channels           # body {platform, channel_id}
DELETE /admin/agents/{name}/bindings/channels/{platform}/{channel_id}
```

依赖 `_require_admin` 守卫（在 `_require_auth` 基础上检查 `is_admin`）。所有写入操作 transactional：创建 agent 时原子写 agents + agent_versions 两行。

### 10. CLI 对等命令

```
fleetent-admin create-agent --name --system-prompt --allowed-tools [--skills-dir] [--mcp-servers] [--memory-namespace]
fleetent-admin update-agent --name --system-prompt [...]              # 创建新版本
fleetent-admin list-agents [--include-deleted]
fleetent-admin show-agent --name [--version N]
fleetent-admin list-agent-versions --name
fleetent-admin activate-agent-version --name --version N
fleetent-admin delete-agent --name
fleetent-admin assign-user --user-id --agent-name
fleetent-admin unassign-user --user-id --agent-name
fleetent-admin promote-admin --user-id
fleetent-admin revoke-admin --user-id
```

复用 `agent_store` 新 API，CLI 只负责 argparse 和 stdout 格式化。

### 11. invoke_agent vs sub_agent 的边界

- `sub_agent`：spawn 一组**匿名 worker**（无独立配置），并行跑同一份父 agent 的工具/系统提示。适合"把一个大任务拆 N 个独立子任务"。
- `invoke_agent`：指定**已注册的 agent 名字**，加载该 agent 自己的 snapshot 跑。适合"我要把这个请求转给客服 agent / 分析 agent"。

二者并存。子 agent 不能调用任何一种（schema 里去除）。

### 12. 为什么不直接禁用旧字段

`Agent.system_prompt` / `Agent.allowed_tools` 在数据类中保留：

- 所有外部代码（含测试）至少要一次性切到新 API，渐进式给迁移留窗口。
- `agent_store.create_agent()` 内部自动创建 version 1 并把字段 mirror 写到 `agent_versions`，旧 CLI 行为不变。
- 列表 API 返回时从 active version 读取并填充到 `Agent` 字段，外部读路径无感。

## Risks / Trade-offs

1. **memories 文件迁移**：用户实际 prod 数据可能在生产 SQLite。提供 migration 脚本（幂等）+ CI 检测；如果不跑迁移，旧 agent 会读不到历史记忆但不会崩。
2. **MCP 默认收紧可能误伤现有 agent**：现存 agent 创建时没有 `mcp_server_ids`，迁移脚本要把它们的初始 version 设成"全部 server"（保持原行为），新建 agent 才默认空。
3. **session 元数据格式变化**：session JSON 结构改 → 兼容老格式：load 时若 `messages` 在顶层视为旧格式，自动包装。
4. **active_version_id 切换的并发**：用 SQLite 单语句 `UPDATE agents SET active_version_id=? WHERE id=?` 原子完成；同一时刻读端不会看到中间状态。
5. **HTTP API 表面积扩大**：所有写操作要求 admin。第一版不做审计日志（已有 eval_logger 覆盖请求层），但 `agent_versions.created_by_user_id` 记录谁创建了版本足够事后追溯。

## Migration Plan

1. 加列：`ALTER TABLE agents ADD COLUMN active_version_id`、`deleted_at`；`users.is_admin`；`channel_agents.bound_version_id`。
2. 建表：`agent_versions`。
3. 一次性脚本：每个现存 agent 创建 version 1（mirror 现有 system_prompt / allowed_tools，mcp_server_ids = 所有当前注册的 server id，memory_namespace = 'default'）；写 `active_version_id`。
4. `scripts/migrate_memories_to_namespace.py` 把每个 user 的 `memories.jsonl` 移到 `memories/default.jsonl`。
5. 至少一个用户提权 `promote-admin` 后才能用新 HTTP API（CLI 不要求 admin，老人沿用 ssh + CLI）。
