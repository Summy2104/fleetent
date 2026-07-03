## ADDED Requirements

### Requirement: MCP server 表单可查看/编辑全部 x-fleetent 扩展字段

React 管理 SPA 的 MCP server 新建/编辑表单 SHALL 提供 `agent.yaml` 每个 MCP server `x-fleetent` 块下全部 4 个 fleetent 扩展字段的查看与编辑入口:`degrade_mode`(降级策略,枚举 degrade/strict/silent)、`file_isolation`(文件隔离,枚举 on/off)、`file_root`(文件根目录,字符串)、`approval_rules`(审批规则列表)。这 4 个字段 SHALL 一直显示,不按 transport 类型隐藏,并归入一个独立分组(建议可折叠)。每个字段下方 SHALL 沿用既有 `field-schema` 机制展示其 `agent.yaml` 路径(`mcpServers.{id}.x-fleetent.<字段>`),不新写一份映射表。

这 4 个字段 SHALL 经 `POST/PUT /admin/mcp/servers` 存入平台管理库 `mcp_servers`(新增对应列;`approval_rules` 以 JSON 存),`GET /admin/mcp/servers` SHALL 在每条 server 记录里回显它们。写入前 SHALL 用 `config.py` 的 `McpServerSettings` / `McpApprovalRule` 校验:非法的 `degrade_mode` 值或结构不合法的 `approval_rules`(缺 `tool`、`when` 非字典)SHALL 被拒绝(422)。materialize 物化托管 agent 的 `agent.yaml` 时 SHALL 把这 4 个字段的非默认值经既有 `_mcp_payload_to_map` 提到该 server 的 `x-fleetent` 块下(`approval_rules` 保留 `when` 条件);全默认值时该 server SHALL NOT 出现 `x-fleetent` 块,保持既有整形不变量。

`approval_rules` 的一条规则形如 `{ tool, when }`:`when` 为 `null`/缺省表示整个工具的每次调用都要审批;`when` 为 `{参数名: [允许值...]}` 表示仅当每个列出参数的调用值都落在其允许值列表里才要审批。表单编辑器 SHALL 支持增删规则、每条规则增删「参数名 + 允许值列表」条件,并把"无条件"如实表达为整工具审批。

#### Scenario: 新建时配置 4 个 x-fleetent 字段并落库

- **WHEN** 管理员在新建表单展开「fleetent 扩展」分组,设 `degrade_mode=strict`、`file_isolation=off`、`file_root=/data`,并加一条 `approval_rules` 规则 `{tool: "manage_email", when: {operation: ["send"]}}` 后保存
- **THEN** SPA 调 `POST /admin/mcp/servers` 带这 4 个字段,`GET /admin/mcp/servers` 该 server 记录回显这 4 个字段的值(`approval_rules` 为结构化列表)

#### Scenario: 物化到托管 agent 的 agent.yaml

- **WHEN** 一个配了非默认 x-fleetent 字段的 MCP server 被物化进某托管 agent 的 `agent.yaml`
- **THEN** 该 server 的 `mcpServers.<id>.x-fleetent` 下出现 `degrade_mode` / `file_isolation` / `file_root` / `approval_rules`(含 `when` 条件),全默认字段不出现

#### Scenario: 非法字段值被拒绝

- **WHEN** 请求体携带不在枚举内的 `degrade_mode`,或 `approval_rules` 里有一条缺 `tool` 字段的规则
- **THEN** 响应为 422,不写入 store

#### Scenario: 整工具审批规则(无 when 条件)

- **WHEN** 管理员为某工具添加一条 `approval_rules` 规则但不加任何「参数条件」
- **THEN** 保存后该规则以 `when: null` 落库,物化出的 `agent.yaml` 中该规则表示"该工具每次调用都要审批"
