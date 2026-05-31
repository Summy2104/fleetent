## 1. 前置核实（实现前的事实确认，无代码改动）

- [x] 1.1 核实 `tool_registry._registry` 的结构（`dict[name, (callable, schema)]`）与 `_risk_levels` 字典（tool_registry.py 行 14-15），确认改键时需同步迁移 `_registry` 与 `_risk_levels` 两处，并更新 schema 内 `function.name`
- [x] 1.2 核实 `mcp_client._make_tool_name` 的双下划线命名空间约定（mcp_client.py 行 53-54）与 `_register_tool_*` 直接写 `tr._registry` 的方式（行 280 / 299），确认插件改键沿用同一命名格式
- [x] 1.3 核实 `agent_store.Agent` 现有字段与 `agents` 表 DDL（agent_store.py 行 13-32、118-129），确认新增 `plugins` 列与字段的读写点（`create_agent` / `get_by_name` / `get_agent_for_user` / `get_agent_for_channel`）
- [x] 1.4 核实**真实授权门**：`agent_loop._safe_dispatch`（agent_loop.py 行 71）调 `dispatch(name, arguments, is_sub_agent=...)` 从不传 `allowed_tools`，故 `tool_registry.dispatch` 内的 `check_tool_access` 分支（tool_registry.py 行 70-74）在生产路径不生效；真实门是 `agent_loop` 暴露给 LLM 前的工具 schema 过滤（agent_loop.py 行 273-274 / 508-510 调 `check_tool_access`），`allowed_tools` 由 server.py 行 186-188 从 `agent.allowed_tools` 构造传入。确认 plugins 展开为 `{name}__*` 并入该构造处的 `allowed_tools`、经 schema 过滤生效，无需改 `check_tool_access` 签名、不依赖 `dispatch` 分支
- [x] 1.5 核实 `skill_registry.scan` 的可注入目录模式（行 31-34，读 env `MINI_AGENT_SKILLS_DIR` 默认目录、`base.is_dir()` 容错；CLAUDE.md 的 `FLEETENT_SKILLS_DIR` 为未落地改名）与 `server.py` lifespan 调用点（行 67-68），据此定 `PLUGINS_DIR`、env 前缀（随改名约定用 `FLEETENT_PLUGINS_DIR`）与加载时机
- [x] 1.6 核实 `agents` 表加列机制：表当前由 `agent_store._init_db` 的 `CREATE TABLE IF NOT EXISTS` 创建（agent_store.py 行 118-129），而仓库另有 `db-migration` spec（alembic + 禁止应用代码裸建表）。确认 `plugins` 列加列方式（走 alembic migration 还是 `_init_db` 幂等扩展），避免裸 `ALTER TABLE ADD COLUMN` 对已存在列重复抛错

## 2. 插件元数据与目录扫描（plugin_loader.py）

- [x] 2.1 Write failing tests for `PLUGINS_DIR` 与 `PluginMeta`：`tests/test_plugin_loader.py` 断言 `PLUGINS_DIR` 默认 `./plugins`、可经 `FLEETENT_PLUGINS_DIR` 覆盖（monkeypatch env）；`PluginMeta` 含 `name` / `enabled` / `path` 字段。运行 `uv run pytest -x -q` 看到红
- [x] 2.2 Implement `PLUGINS_DIR`（模块级常量）、`PluginMeta`（frozen dataclass）、目录解析辅助（读 env，仿 skill_registry），看到绿
- [x] 2.3 Write failing tests for 目录扫描：`tmp_path` 造插件目录树，monkeypatch `plugin_loader.PLUGINS_DIR`；目录不存在时返回空、不抛；只识别含 `plugin.yaml` 的子目录。看到红
- [x] 2.4 Implement 扫描逻辑（遍历子目录、读 `plugin.yaml`、解析元数据），看到绿

## 3. enabled 过滤与命名空间化加载

- [x] 3.1 Write failing tests for enabled 过滤：`enabled: true` 的插件被加载，`enabled: false` 或缺省的被跳过且不 import。看到红
- [x] 3.2 Implement enabled 过滤（仅对 `enabled` 为真者继续 import），看到绿
- [x] 3.3 Write failing tests for 命名空间化：插件 `__init__.py` 含一个 `@tool def foo`，加载后 `tool_registry.get_schemas()` 出现 `{插件名}__foo`、不再单独出现 `foo`；schema 内 `function.name` 为命名空间名；`get_risk_level("{插件名}__foo")` 保留原 risk_level。另加守卫：插件 `__init__.py` 间接 import `fleetent.tools`（注册副作用模块）时，既有内置/MCP 工具键不被改写或纳入命名空间化（仅本插件包内定义的 `@tool` 被改键）。看到红（用 `tmp_path` 造可 import 的插件包并加入 `sys.path`，registry 用 monkeypatch/清理隔离）
- [x] 3.4 Implement 命名空间化（import 前后 diff `_registry` 新增键，只对本插件包内定义的新键改键——按 `__module__` 归属判定，排除间接 import 的既有模块工具，改键 `_registry` 与 `_risk_levels`，更新 schema name），看到绿

## 4. 容错：格式错误 / import 失败跳过并告警

- [x] 4.1 Write failing tests for 容错：`plugin.yaml` 非法 YAML / 顶层非 mapping / 缺 `name` → 跳过且不抛、其余插件仍加载、发出 warning；`__init__.py` import 抛异常 → 跳过该插件、其余仍加载、发出 warning。看到红
- [x] 4.2 Implement 每插件 try/except 包裹（仿 mcp_client.register_all），失败 `logger.warning` 并 continue，看到绿
- [x] 4.3 Write failing test 守卫 `test_one_bad_plugin_does_not_block_others`：两个插件目录，一个坏一个好，`load_plugins()` 仍加载好的那个的工具。看到红
- [x] 4.4 Implement 使守卫通过（确认单插件失败不中断遍历），看到绿
- [x] 4.5 Write failing tests for 命名空间唯一性（D6）：插件名与已注册 MCP server_id / 内置工具命名空间前缀冲突、或两插件同名时，冲突插件被跳过 + warning，既有同名命名空间工具键不被改写，其余插件仍加载。看到红
- [x] 4.6 Implement 加载入口前置唯一性校验（插件名全局唯一，冲突 `logger.warning` + 跳过，不改写既有键），看到绿

## 5. agent 授权字段（agent_store.py + plugins 展开）

- [x] 5.1 Write failing tests for `Agent.plugins` 字段：`create_agent(..., plugins=["crm_tools"])` 后 `get_by_name` 读回 `plugins == ["crm_tools"]`；不传 `plugins` 时默认 `[]`；旧库（无 plugins 列）读取默认 `[]` 向后兼容。`monkeypatch agent_store.DB_PATH` 隔离到 `tmp_path`。看到红
- [x] 5.2 Implement `Agent` 加 `plugins: list[str]` 字段、`agents` 表加 `plugins TEXT NOT NULL DEFAULT '[]'`（加列方式依 1.6 的核实结论——alembic 或 `_init_db` 幂等扩展，不重复裸 ALTER）、各读写点 JSON 序列化，看到绿
- [x] 5.3 Write failing tests for plugins 展开授权：`expand_plugin_patterns(["crm_tools"]) == ["crm_tools__*"]`；把展开结果并入 `allowed_tools` 后，未授权插件工具不出现在暴露给 LLM 的工具 schema 列表中——断言 `agent_loop` 的 schema 过滤（`crm_tools__lookup` 在含 `crm_tools__*` 时出现、不含时被过滤掉），而非断言 `dispatch`。看到红
- [x] 5.4 Implement `expand_plugin_patterns` 辅助，并在构造 agent 有效 `allowed_tools` 的位置（server.py 行 186-188 / CLI run 入口）并入展开模式，使其经 `agent_loop` schema 过滤生效，看到绿

## 6. 启动时加载（server.py lifespan）

- [x] 6.1 Write failing tests：lifespan 启动调用 `plugin_loader.load_plugins()`（patch `load_plugins` 断言被调用一次）；不存在 `plugins/` 目录时启动不报错。看到红
- [x] 6.2 Implement lifespan 中调用 `load_plugins()`（紧随 `scan_skills()`），看到绿

## 7. 收尾

- [x] 7.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`），无回归
- [x] 7.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿
- [x] 7.3 `uv run mypy src` 无新增错误模式
