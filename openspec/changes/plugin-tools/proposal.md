## Why

平台目前的工具只有两个来源：`tools.py` 的内置工具（import 副作用经 `@tool` 注册）与 `mcp_client` 注册的远程 MCP 工具（`{server_id}__{tool_name}` 命名空间）。企业团队若想给自己的 agent 加一个内部工具（如查 CRM、查工单系统），唯一途径是改 `src/fleetent/tools.py` 并重新部署平台代码——这违背「on-premises 部署、团队自助扩展」的定位：每个客户的私有工具都要侵入平台源码，无法隔离、无法按 agent 授权。

这是 AR7（插件工具机制）。它给出第三个工具来源：**插件目录**。企业团队在 `plugins/{插件名}/` 放一个 `plugin.yaml` + `__init__.py`（内含 `@tool` 函数），平台启动时自动扫描加载 `enabled: true` 的插件，工具自动加命名空间前缀 `{插件名}__{工具名}`（双下划线，与 MCP `{server}__{tool}` 约定一致——单下划线是工具名的一部分）。agent 定义须在 `plugins: [...]` 白名单里显式列出插件名，否则该插件的工具对该 agent 不可见。如此，扩展工具无需触碰平台代码，且每个 agent 只看见被授权的插件工具。

## What Changes

- 新增**插件加载层**（建议 `src/fleetent/plugin_loader.py`）：扫描可注入的插件目录常量 `PLUGINS_DIR`（支持 `FLEETENT_PLUGINS_DIR` 环境变量覆盖，与 skill 目录的 env 覆盖同模式——注意代码现状前缀为 `MINI_AGENT_`，本变更随改名约定采用 `FLEETENT_PLUGINS_DIR`），对每个含 `plugin.yaml` 的子目录读取元数据。
- **仅加载 `enabled: true` 的插件**：`plugin.yaml` 中 `enabled` 缺省或为 `false` 的插件被跳过。
- **复用现有 `@tool` 注册**：加载器 import 插件包的 `__init__.py`，触发其中 `@tool` 函数的注册副作用；随后把这些新注册的工具在 `tool_registry` 中**重命名为命名空间形式** `{插件名}__{工具名}`（双下划线），保留原 schema 与 risk_level。
- `plugin.yaml` **格式错误**（缺 `name`、非法 YAML、`__init__.py` import 失败等）→ **跳过该插件并 `logger.warning`，不阻断启动**，其余插件正常加载（仿 `mcp_client.register_all` 与 `skill_registry.scan` 的容错风格）。
- **agent 授权**：`agents` 表与 `Agent` 数据类新增 `plugins: list[str]` 字段（默认空列表，向后兼容）；agent 仅能调用其 `plugins` 列表覆盖的插件工具。授权检查复用既有 `agent_policy` / `allowed_tools` 机制——把 agent 的 `plugins` 展开为命名空间通配模式（`{插件名}__*`）并入 `allowed_tools` 的构造处（server.py:186-188 / run 入口），再由 `agent_loop` 暴露给 LLM 的工具 schema 过滤（agent_loop.py:273-274、508-510 调 `check_tool_access`）判定：未授权的插件工具不出现在暴露给 LLM 的工具列表中、不可被调用。
- 平台启动时（FastAPI lifespan）调用插件加载，与 `skill_registry.scan()` / `mcp_client.register_all()` 并列。

## Capabilities

### New Capabilities
- `plugin-tools`: 企业团队无需修改平台代码即可扩展工具——在 `plugins/{插件名}/` 放 `plugin.yaml` + `__init__.py`（含 `@tool` 函数），平台启动时扫描可注入的 `PLUGINS_DIR`，仅加载 `enabled: true` 的插件，工具自动加 `{插件名}__{工具名}`（双下划线）命名空间前缀；`plugin.yaml` 格式错误跳过并告警不阻断启动；agent 须在 `plugins` 白名单列出插件名方可调用其工具，授权经既有 `agent_policy` 判定。

### Modified Capabilities
- `agent-definition`: `Agent` 数据类与 `agents` 表新增 `plugins: list[str]` 字段（修改既有「Agent definition storage」与「Schema」需求），并把 agent 的 `plugins` 展开为命名空间模式 `{插件名}__*` 纳入工具访问控制白名单判定（修改既有「allowed_tools wildcard support」需求）——这是对既有 agent 定义与访问控制行为的需求级扩展，见 `specs/agent-definition/spec.md`。

## Impact

- **代码**：
  - 新增 `src/fleetent/plugin_loader.py`（`PLUGINS_DIR` 可注入常量 + `PluginMeta` 数据类 + `load_plugins()` 扫描/加载/命名空间化 + 容错跳过）。
  - 修改 `src/fleetent/agent_store.py`：`Agent` 数据类新增 `plugins: list[str]` 字段；`agents` 表加 `plugins TEXT NOT NULL DEFAULT '[]'` 列（加列方式见前置核实——确认走 db-migration（alembic）还是 `_init_db` 幂等扩展，避免对已存在列重复 `ALTER TABLE` 抛错）；`create_agent` / 各 `get_*` 读写该字段（JSON 序列化，沿用 `allowed_tools` 的存法）。
  - 修改 `src/fleetent/server.py`（及 CLI run 入口）：把 agent 的 `plugins` 经新增展开辅助函数（`{插件名}__*`）并入构造 `allowed_tools` 的位置（server.py:186-188），交由 `agent_loop` 的工具 schema 过滤（agent_loop.py:273-274、508-510 调 `check_tool_access`）判定，使未授权插件工具不暴露给 LLM。不改 `check_tool_access` 纯函数签名；不依赖 `tool_registry.dispatch` 内的访问控制分支（`_safe_dispatch` 从不传 `allowed_tools`，该分支在生产路径不生效）。
  - 修改 `src/fleetent/server.py`：lifespan 中调用 `plugin_loader.load_plugins()`，与 `scan_skills()` 并列。
- **配置**：
  - 新增环境变量 `FLEETENT_PLUGINS_DIR`（覆盖默认 `./plugins`），与 skill 目录的 env 覆盖同模式（代码现状 skill 用 `MINI_AGENT_SKILLS_DIR`，本变更随改名约定采用 `FLEETENT_` 前缀）；不引入 Settings 字段（目录解析在加载器内读 env，仿 `skill_registry.scan`）。
  - 新增 `plugins/` 目录约定（gitignored 客户私有插件，仅约定结构，不入库具体插件）。
- **测试**：
  - 新增 `tests/test_plugin_loader.py`：插件目录隔离到 `tmp_path` 并 monkeypatch `PLUGINS_DIR`；覆盖 enabled 过滤、命名空间化、格式错误跳过、import 失败跳过。
  - `tests/test_agent_store.py` 补充 `plugins` 字段读写与默认空列表向后兼容用例。
  - 补充 plugins 展开为命名空间模式的授权用例：展开结果并入 `allowed_tools` 后，未授权插件工具不出现在暴露给 LLM 的工具 schema 列表中（断言 `agent_loop` 的 schema 过滤，而非 `dispatch`）。
  - 加载器测试断言：插件 import 不改写既有内置/MCP 工具键（仅新增本插件的命名空间键）；插件名与已注册 MCP server_id / 内置工具前缀冲突时跳过并告警。
  - 所有测试不触碰真实 `plugins/` 与 `data/`，全部 `tmp_path + monkeypatch` 隔离。
- **不影响**：内置工具注册、MCP 工具注册、permission_gate、context 压缩、终止与错误分类、im_gateway。
- **依赖**：无新增依赖——使用标准库（`importlib` / `pathlib`）+ 既有 `pyyaml`。
