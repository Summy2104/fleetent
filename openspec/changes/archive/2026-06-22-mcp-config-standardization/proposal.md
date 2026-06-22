## Why

fleetent 的 MCP server 配置用的是私有的 `list-of-id` 外形,与生态事实标准(Claude Desktop 起源、claude-code/opencode/openclaw/Hermes 一致采用的 `mcpServers` map)不兼容——标准配置块无法直接粘贴。同时 MCP 工具名硬编码为 `{server_id}__{tool_name}`,与其它 agent 平台各异,导致同一个调用 MCP 的 skill 无法跨平台复用。本次让配置「drop-in 可粘贴」、工具名「按平台投影可配」,且**完全保留** fleetent 的治理/沙箱/自托管特性。

## What Changes

- **BREAKING** MCP server 配置从 `list-of-id` 改为事实标准 **map-keyed-by-name**:顶层 key 同时接受 `mcpServers` 与 `mcp_servers`;核心字段对齐标准(`command`/`args`/`env` | `url`/`headers`/`type`);**transport 自动判定**(有 `command`→stdio,有 `url`→remote);env 引用用 `${VAR}` 语法。**不保留旧 list 解析(clean cutover,生产手动迁移)。**
- fleetent 特有能力收进每个 server 下的嵌套厂商扩展块 **`x-fleetent`**(标准解析器忽略):`degrade_mode`、`file_root`/`file_isolation`(沙箱 `/exchange` 桥接)、`auth`(自托管 OAuth2:`token_url`/`client_id`/`client_secret_env`/`scope`,禁云)、`approval_rules`(per-tool 审批)。
- 新增**声明式模板的工具名投影**:配置 `mcp.tool_naming`(预设词 `claude`|`hermes`|`opencode`|`skills`|`bare`,或自定义 `{template, sanitize, max_len}`)。投影引擎写一次、平台无关;新增平台只需加一行配置,无需改代码。
- **BREAKING** 默认工具名约定从 `{server}__{tool}` 改为 **`mcp__{server}__{tool}`**(默认 `tool_naming: claude`,对齐最权威/无歧义约定)。
- 投影实现为 **LLM 边界 in/out 翻译**:registry 始终以 canonical 注册;反查表(投影名→`(server_id, raw_tool)`)为 agent 进程内瞬态,注册期构建、缓存复用。`governance/approval_policy` 改为读注册的 `(server_id, raw_tool)` 元数据判定 MCP 风险,**不再按 `__` 切字符串**(根因加固,确保任何 `tool_naming` 下审批不被绕过)。

不在本次范围(留作后续单独立项):平台 DB/admin 路径(`mcp_server_store` 表、`connector_admin_api`、`mcp_runtime`)维持现状,仍只存标准子集、不承载 `x-fleetent`。

## Capabilities

### New Capabilities
- `mcp-tool-name-projection`: agent 侧声明式模板的 MCP 工具名投影——`mcp.tool_naming` 预设/自定义模板;LLM 边界 in/out 翻译 + canonical 反查表;保证 governance(审批/访问控制)绑定 `(server_id, raw_tool)` 而非投影名,任何命名下审批/拦截不变。

### Modified Capabilities
- `mcp-client`: MCP server 配置外形改为标准 `mcpServers` map + `x-fleetent` 扩展块 + transport 自动判定 + `${VAR}`(替代旧 list-of-id);工具命名约定由固定 `{server}__{tool}` 改为投影驱动、默认 `mcp__{server}__{tool}`。

## Impact

- **Owning package(agent 侧)**:`integrations/mcp`(投影引擎 + 反查表,新模块 `tool_naming.py`)、`agent_config`(读 agent.yaml 新外形)、`config`(共享 `McpServerSettings`/`XFleetentExt`/`tool_naming` 模型)。
- **Public API**:`McpServerConfig` 内部契约不变;新增 `mcp.tool_naming` 配置项与 `integrations/mcp/tool_naming` 投影模块。
- **Owned tables**:无(平台 DB/admin 路径本轮不动)。
- **Config namespace**:`mcpServers`/`mcp_servers`(map)、`x-fleetent.*`、`mcp.tool_naming`。
- **Cross-module deps**:`governance.approval_policy`(改读 `(server, raw_tool)` 元数据,保持绑原始工具名)、`tools.registry`(工具名暴露经边界 shim)。
- **Platform 侧(仅写纽带)**:`platform/agent_lifecycle/materialize.py` 渲染 agent.yaml 时只产出新 map 格式——属 platform→agent 经 agent.yaml 的既有合法方向,不引入反向依赖。
- **解耦**:投影逻辑/反查表 100% 在 agent 侧(`integrations/mcp` MUST NOT import platform);`fleetent agent run` 独立运行只读 agent.yaml 即可建表投影,不依赖 platform/DB。
- **BREAKING / 迁移**:旧 `list-of-id` agent.yaml 与旧工具名 `{server}__{tool}` 不再兼容;生产环境由运维手动迁移(clean cutover)。`agent.yaml.example` 同步更新。
