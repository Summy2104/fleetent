## 1. 配置解析:标准 map + x-fleetent(替代 list-of-id)

- [x] 1.1 写测试:`mcpServers`/`mcp_servers` map 解析、transport 自动判定(command→stdio / url→remote)、`${VAR}` 引用、`x-fleetent` 字段、legacy list 被拒(见红)
- [x] 1.2 实现 `config.py`:`McpServerSettings` 改 map-keyed + 新增 `XFleetentExt`(degrade_mode/file_root/file_isolation/auth/approval_rules);解析两种顶层 key + transport 自动判定 + `${VAR}`(见绿)
- [x] 1.3 写测试:`agent_config.AgentFile` 读 agent.yaml 新外形 + 序列化 round-trip(红)
- [x] 1.4 实现 `agent_config.py` 的 `mcp_servers` 新外形解析/序列化(绿)
- [x] 1.5 写测试:`McpServerSettings`→`McpServerConfig` 映射(map key→`id`、`x-fleetent.*`→对应字段;`McpServerConfig` 契约不变)(红)
- [x] 1.6 实现映射层(绿)

## 2. 工具名投影引擎(声明式模板)

- [x] 2.1 写测试:投影引擎——预设 `claude`/`hermes`/`opencode`/`skills`/`bare`、自定义 `template`、`sanitize`、`max_len`、默认 `claude`(红)
- [x] 2.2 实现新模块 `integrations/mcp/tool_naming.py`(模板渲染引擎,平台无关)(绿)
- [x] 2.3 写测试:`McpSettings.tool_naming` 配置解析(预设词 与 `{template, sanitize, max_len}` 两种形态)(红)
- [x] 2.4 实现 `McpSettings` 增加 `tool_naming` 字段(绿)

## 3. 投影接入 + canonical 元数据 + 审批加固(安全核心)

- [ ] 3.1 写测试:registry 按 canonical 注册 + 反查表 `投影名→(server_id, raw_tool)` + schema 出站投影 + tool_use 入站还原(含单下划线歧义场景如 `google_drive`)(红)
- [ ] 3.2 实现 `integrations/mcp/client.py`:canonical 注册、存 `(server_id, raw_tool)` 元数据、注册期构建反查表(缓存)、LLM 边界 in/out 翻译(绿)
- [ ] 3.3 写测试(防回归核心):每种 `tool_naming`(claude/hermes/bare)下 `approval_rules` 仍命中、`permission_gate` 仍拦截、只读工具不过度 gate;`allowed_tools` 匹配行为不变(红)
- [ ] 3.4 实现 `governance/approval_policy`:MCP 风险改读注册的 `(server_id, raw_tool)` 元数据,移除 `partition("__")` 字符串切分(绿)

## 4. 物化 + 样例 + 文档

- [ ] 4.1 写测试:`materialize` 渲染的 agent.yaml 为新 `mcpServers` map 格式(红)
- [ ] 4.2 实现 `platform/agent_lifecycle/materialize.py` 只产出新 map 格式(绿)
- [ ] 4.3 更新 `agents/default/agent.yaml.example`:新 map + `x-fleetent` 块 + `mcp.tool_naming` 示例
- [ ] 4.4 更新 `docs/capabilities/mcp.md`:配置格式(map+x-fleetent)、transport 自动判定、`tool_naming` 投影与默认命名约定

## 5. 收尾验证

- [ ] 5.1 `make test-pr` 全绿(判据「无新增失败」)+ 改动文件 ruff
- [ ] 5.2 `fleetent agent run` 独立冒烟:无 platform 下读 agent.yaml 建表投影、MCP 工具按默认 `mcp__{server}__{tool}` 暴露、审批正常
- [ ] 5.3 模块边界:`PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` 确认 `integrations/mcp` 不 import platform
