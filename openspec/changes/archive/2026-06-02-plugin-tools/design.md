## Context

平台当前有两个工具来源，注册方式不同但终点一致——都落到 `tool_registry._registry`（`dict[name, (callable, schema)]`）：

- **内置工具**：`tools.py` 顶部被 import（`agent_loop.py` 行 14 `import fleetent.tools`），其中的 `@tool` 函数在 import 副作用中注册，工具名 = 函数名。
- **MCP 工具**：`mcp_client._register_tool_stdio/http`（行 280 / 299）直接写 `tr._registry[tool_name] = (call, schema)`，名字经 `_make_tool_name(server_id, tool_name)` 加 `{server_id}__{tool_name}` 双下划线前缀（mcp_client.py 行 53-54）。
- **访问控制**：`agent_policy.check_tool_access(tool_name, allowed_tools)` 用 `fnmatch` 对 `allowed_tools` 白名单逐条匹配（agent_policy.py 行 4-5）；`tool_registry.dispatch` 在 `allowed_tools is not None` 时调用它。`agent_store.Agent` 现有字段为 `id / name / system_prompt / allowed_tools`，无 `plugins`。

插件工具是第三个来源。它要既复用 `@tool`（让插件作者只需理解一个装饰器，符合 tools.md「`@tool` 是工具作者唯一需要理解的接口」），又像 MCP 一样加命名空间前缀避免插件间/与内置工具重名，还要受 agent 级授权约束。

约束（CLAUDE.md）：禁止 AI 框架；禁止 ORM（`agents` 表用 stdlib sqlite3 直接 SQL）；禁止全局可变状态（`PLUGINS_DIR` 为模块级常量，测试可 monkeypatch）；新模块结构 import → 常量 → 数据类 → 函数；mypy strict；行长 100；TDD Hard Gate；测试隔离插件目录到 `tmp_path`；不吞异常（容错跳过处必须 `logger.warning`）。本功能无需新依赖。

依赖顺序：本 change 复用既有的 `tool_registry`（`@tool` 注册 + `_registry` 命名空间约定）、`agent_policy.check_tool_access`、`agent_loop` 的工具 schema 过滤（暴露给 LLM 前的真实授权门）、`agent_store.Agent`/`agents` 表、`server.py` lifespan（与 `scan_skills()` 并列的加载时机），以及 `mcp_client` 既有的 `{server_id}__{tool_name}` 命名空间约定。修改触及 capability `agent-definition`（`Agent`/`agents` 表加 `plugins`、把 plugins 展开纳入 `allowed_tools` 判定）；加列方式与 `db-migration` capability 相关，需前置核实加列走 alembic 还是 `_init_db`。无新增依赖。

## Goals / Non-Goals

**Goals:**
- 提供 `plugin_loader.load_plugins()`：扫描 `PLUGINS_DIR`，对每个含 `plugin.yaml` 的子目录加载 `enabled: true` 的插件。
- 复用 `@tool` 注册：import 插件 `__init__.py` 触发注册副作用，随后把新注册的工具改键为 `{插件名}__{工具名}`（双下划线），保留 schema 与 risk_level。
- `PLUGINS_DIR` 可注入（默认 `./plugins`，`FLEETENT_PLUGINS_DIR` 覆盖），仿 `FLEETENT_SKILLS_DIR`。
- `plugin.yaml` 格式错误 / `__init__.py` import 失败 → 跳过该插件并 `logger.warning`，不阻断启动，其余插件继续。
- `Agent` 数据类与 `agents` 表加 `plugins: list[str]`（默认空，向后兼容）；把 agent 的 `plugins` 展开为命名空间模式参与既有 `agent_policy` 授权判定，未列出的插件工具对该 agent 不可见。
- FastAPI lifespan 启动时加载插件，与 `scan_skills()` 并列。

**Non-Goals:**
- 不做插件热重载 / 运行时启停（仅启动时一次性加载；CLI 单次 `run()` 的加载时机见 Open Questions）。
- 不做插件依赖安装 / 版本求解 / 沙箱隔离执行（插件代码与平台同进程运行，信任边界 = 部署方放进 `plugins/` 的代码即受信，与内置工具同级）。
- 不实现插件工具的超时保护（属 tools.md「工具超时保护」AR，本次不越界）。
- 不引入新依赖、不新增 Settings 字段（目录解析在加载器内读 env）。
- 不改动内置工具、MCP 工具、permission_gate、错误分类的既有行为。

## Decisions

### D1：插件加载层 `plugin_loader.py`，复用 `@tool` 注册 + 加载后改键
新增 `src/fleetent/plugin_loader.py`：
- `PLUGINS_DIR: str`：模块级常量，默认 `./plugins`，加载器内 `os.environ.get("FLEETENT_PLUGINS_DIR", PLUGINS_DIR)` 解析（仿 `skill_registry.scan`，可 monkeypatch）。注意：`skill_registry.scan`（skill_registry.py:34）当前读的是 `MINI_AGENT_SKILLS_DIR`，CLAUDE.md 的 `FLEETENT_SKILLS_DIR` 是尚未落地的改名约定；本变更随该约定直接采用 `FLEETENT_PLUGINS_DIR` 前缀。
- `PluginMeta`（frozen dataclass）：`name: str`、`enabled: bool`、`path: str`（+ 可选 `version` / `description`，仅作展示）。
- `load_plugins(plugins_dir: str | None = None) -> list[PluginMeta]`：遍历子目录，读 `plugin.yaml`，跳过 `enabled` 非真者；对启用项，`importlib` 导入其包，**比对 import 前后 `tool_registry._registry` 的新增键**，把新增键改为 `{name}__{原键}`（保留同一 `(callable, schema)`，schema 内的 function name 同步更新）。

**为何**：插件作者只写 `@tool`（与内置工具体验一致，符合 tools.md 契约），不必学新装饰器；命名空间前缀在加载层统一施加，避免插件作者手写前缀出错、也避免插件间/与内置工具重名。「import 前后 diff registry」是把「函数名注册」转成「命名空间注册」的最小侵入做法，无需改 `@tool` 或 `tool_registry`。
**Alternatives**：①新增 `@plugin_tool` 装饰器让插件直接注册带前缀的名——被否，增加插件作者认知负担，且与 tools.md「`@tool` 是唯一接口」相悖；②让 `tool_registry` 感知「当前正在加载哪个插件」的上下文变量，注册时自动加前缀——被否，引入隐式全局状态（违反禁止全局可变状态），且 `@tool` 要硬编码插件耦合；③插件直接写 `tr._registry[...]` 仿 MCP——被否，绕过 `@tool` 契约，插件作者要理解内部 registry 结构。

### D2：命名空间前缀用双下划线 `{插件名}__{工具名}`
与 MCP `_make_tool_name`（`{server_id}__{tool_name}`）完全一致：双下划线分隔，单下划线视为名字的一部分（CLAUDE.md gotcha）。
**为何**：全平台命名空间约定统一，agent 的 `allowed_tools` / `plugins` 通配模式（`crm_tools__*`）对 MCP 与插件语义一致，减少认知分叉。
**Alternatives**：用 `.` 或 `:` 分隔——被否，与既有 MCP 约定不一致，且部分 schema 校验对工具名字符集敏感。

### D3：agent 授权——`plugins` 展开并入有效 `allowed_tools`，由暴露给 LLM 前的 schema 过滤施加
- `Agent` 加 `plugins: list[str]`（默认 `[]`）；`agents` 表加 `plugins TEXT NOT NULL DEFAULT '[]'`（JSON 串，沿用 `allowed_tools` 的 `json.dumps/loads` 存法）。
- 不改 `check_tool_access(tool_name, allowed_tools)` 纯函数签名；新增辅助（如 `plugin_loader.expand_plugin_patterns(plugins) -> list[str]`，把 `["crm_tools"]` 映射为 `["crm_tools__*"]`）。
- **真实授权门是 `agent_loop` 暴露给 LLM 前的工具 schema 过滤**（agent_loop.py:273-274 在 `run()`、508-510 在 `run_stream()`：对每个工具 schema 调 `check_tool_access(name, allowed_tools)`，未通过者从暴露给 LLM 的列表中剔除）。`allowed_tools` 由 server.py:186-188 从 `agent.allowed_tools` 取出后传入；本设计在该构造点（server.py:186-188 / CLI run 入口）把 `expand_plugin_patterns(agent.plugins)` 的结果并入 `allowed_tools`。
- agent 的 `plugins` 未列出的插件工具：其命名空间前缀不在任何通配模式内 → schema 过滤将其排除 → 不出现在暴露给 LLM 的工具列表中，LLM 无从调用，对该 agent 不可见。
- **不依赖 `tool_registry.dispatch` 内的访问控制分支**（tool_registry.py:70-74）：`agent_loop._safe_dispatch` 调 `dispatch(name, arguments, is_sub_agent=...)`（agent_loop.py:71）从不传 `allowed_tools`，故该分支在生产路径不生效（仅测试触发）。把授权点定在 schema 过滤即可观察、即真实生效。

**为何**：复用既有的、生产路径上真实生效的访问控制出口（`agent_loop` 的 schema 过滤 + `agent_policy.check_tool_access`），不新增第二套授权判定；`plugins` 与 `allowed_tools` 关注点分离——`allowed_tools` 控具体工具名/通配，`plugins` 是「插件级开关」，展开后归一到同一 fnmatch 判定。默认空列表保证既有 agent 行为不变（看不见任何插件工具）。
**Alternatives**：①让用户直接在 `allowed_tools` 写 `crm_tools__*`，不加 `plugins` 字段——被否，文档 agent-runtime.md 明确要求 `plugins: [crm_tools]` 这一显式声明（插件级授权语义比通配模式更易审计）；②在 `dispatch` 里单独加一层 plugin 检查——被否，重复授权逻辑且 `dispatch` 当前未接 `allowed_tools`，是生产路径上的死分支。

### D4：容错——格式错误/import 失败跳过并告警，不阻断启动
`load_plugins` 对每个插件目录用 try/except 包裹（仿 `mcp_client.register_all` 行 117-122 / `skill_registry.scan` 行 41-47）：
- `plugin.yaml` 缺失 / 非法 YAML / 顶层非 mapping / 缺 `name` → `logger.warning("plugin_manifest_invalid", path=..., reason=...)`，跳过。
- `__init__.py` import 抛异常 → `logger.warning("plugin_import_failed", name=..., error=...)`，跳过（不吞——以 warning 形式 log，符合 CLAUDE.md「catch 后必须 log 或 re-raise」）。
- 单个插件失败不影响其余插件加载。

**为何**：on-premises 多客户场景下，一个坏插件不应拖垮整个平台启动；与 MCP server 不可用、skill frontmatter 解析失败的容错风格一致。
**Alternatives**：启动即抛、拒绝启动——被否，运维体验差，一个客户的私有插件错误不该阻断平台。

### D5：加载时机——lifespan 启动一次，与 scan_skills 并列
`server.py` lifespan（行 67-110）在 `scan_skills()` 之后调用 `plugin_loader.load_plugins()`。
**为何**：与 skill 扫描、MCP 注册同生命周期；插件工具在服务接受请求前就位。`@tool` 注册是 import 副作用、registry 是模块级，启动时加载一次即对全进程可见——与 tools.md「import 副作用注册」「scan 在 lifespan 跑一次」一致。
**Alternatives**：每次请求加载——被否，重复 import 与改键开销大且无收益（插件目录启动后不变）。

### D6：插件名命名空间全局唯一校验（加载入口前置）
插件名与 MCP server_id、内置工具命名空间共享同一命名空间。加载入口 SHALL 对每个待加载插件做全局唯一性校验：插件名不得与已注册的 MCP server_id、内置工具命名空间前缀冲突，两插件之间名字不得重复。冲突即**跳过该插件 + `logger.warning`**，不改写既有工具键。改键时若目标命名空间名已存在，也按同一策略跳过该工具并告警。
**为何**：插件加载是「import 前后 diff `_registry` 新增键」，若不先做唯一性校验，命名冲突会静默覆盖既有工具键，破坏内置/MCP 工具。前置校验把冲突在 import 前拦截，符合容错风格（坏插件不阻断启动）。该决策由原 Open Question 提升而来——结论是「跳过冲突 + warning」，且唯一性在加载入口前置校验。
**Alternatives**：冲突时硬报错拒绝启动——被否，与 D4 容错原则不一致；冲突时后者覆盖前者——被否，会静默破坏既有工具。

## Risks / Trade-offs

- [插件代码与平台同进程、同信任级运行] → 明确 Non-Goal：插件不做沙箱隔离，信任边界即「谁能写 `plugins/` 目录」。on-premises 部署由运维控制目录写权限；文档与 spec 标注此信任假设。
- [import 前后 diff registry 的做法依赖 `tool_registry._registry` 内部结构] → 这是已被 `mcp_client` 采用的既成内部契约（直接写 `tr._registry`）；改键逻辑集中在 `plugin_loader` 一处，registry 结构若变只此一处随动。加守卫测试断言改键后 `get_schemas()` 含命名空间名且原函数名不再单独存在。
- [插件 import 顺序导致工具名冲突（两个插件各有同名函数）] → 加前缀后 `{A}__{f}` 与 `{B}__{f}` 不冲突；同一插件内重名由 Python 函数定义本身约束。插件名级冲突（与 MCP server_id / 内置前缀 / 另一插件同名）由 D6 的前置唯一性校验拦截——跳过 + warning，不改写既有键。
- [插件 `__init__.py` 间接 import 注册副作用模块污染 diff] → 「import 前后 diff `_registry` 新增键」假设 import 这一刻只多出本插件键；若插件 `__init__.py` 间接 import 了 `fleetent.tools` 等注册副作用模块，会把那些既有工具误纳入命名空间化。缓解：①命名空间化只对「import 前 registry 中不存在、且函数定义于本插件包内（按 `__module__` 归属判定）」的新键施加；②加守卫测试断言插件 import 不改写既有内置/MCP 工具键（见 tasks 3.3/3.4）。
- [`plugins` 新列的既有库迁移] → `agents` 表当前由 `agent_store._init_db` 的 `CREATE TABLE IF NOT EXISTS`（agent_store.py:118-129）创建；裸 `ALTER TABLE ADD COLUMN` 对已存在列会抛错。仓库另有 `db-migration` spec（alembic + 「禁止应用代码裸建表」）。加列方式（走 alembic migration 还是 `_init_db` 幂等扩展）须在前置核实中确认后再实现，避免重复 ALTER 抛错；无论哪种，旧行默认空列表，行为不变。
- [CLI `run()` 不经 lifespan，插件不会被加载] → 见 Open Questions；本次先定 server 路径，CLI 加载时机作为开放项。

## Open Questions

- CLI `run()`（每次调用、不经 FastAPI lifespan）是否需要也加载插件？若需要，是每次 `run()` 都 `load_plugins()`（与 `skill_registry.scan()` 在 CLI 的每次调用一致），还是仅 server 支持插件？倾向前者，实现首步确认 CLI 入口结构后定。
- `plugin.yaml` 是否需要声明导出哪些工具名（显式 allowlist），还是「`__init__.py` 里所有 `@tool` 全部导出」？本设计默认后者（最简）；若需精细控制，`plugin.yaml` 可加 `tools: [...]` 白名单，作为后续增强。
