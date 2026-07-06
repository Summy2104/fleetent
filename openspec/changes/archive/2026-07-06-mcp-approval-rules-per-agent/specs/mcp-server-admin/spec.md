## MODIFIED Requirements

### Requirement: MCP server 表单可查看/编辑全部 x-fleetent 扩展字段

React 管理 SPA 的 MCP server 新建/编辑表单 SHALL 提供 `agent.yaml` 每个 MCP server `x-fleetent` 块下**服务级** fleetent 扩展字段的查看与编辑入口:`degrade_mode`(降级策略,枚举 degrade/strict/silent)、`file_isolation`(文件隔离,枚举 on/off)、`file_root`(文件根目录,字符串)。这些字段 SHALL 一直显示,不按 transport 类型隐藏,并归入一个独立分组(带分隔的小标题)。每个字段下方 SHALL 沿用既有 `field-schema` 机制展示其 `agent.yaml` 路径(`mcpServers.{id}.x-fleetent.<字段>`),不新写一份映射表。

这些字段 SHALL 经 `POST/PUT /admin/mcp/servers` 存入平台管理库 `mcp_servers`,`GET /admin/mcp/servers` SHALL 在每条 server 记录里回显它们。写入前 SHALL 校验:非法的 `degrade_mode`/`file_isolation` 枚举值 SHALL 被拒绝(422)。materialize 物化托管 agent 的 `agent.yaml` 时 SHALL 把这些字段的非默认值经既有 `_mcp_payload_to_map` 提到该 server 的 `x-fleetent` 块下;全默认值时该 server SHALL NOT 出现这些键,保持既有整形不变量。

`approval_rules` **不再是服务级字段**,不在 MCP 服务表单出现,也不由 `POST/PUT/GET /admin/mcp/servers` 承载——它改为 per-agent 绑定级配置(见 `agent-mcp-binding` capability)。

#### Scenario: 新建时配置服务级 x-fleetent 字段并落库

- **WHEN** 管理员在新建表单展开「fleetent 扩展」分组,设 `degrade_mode=strict`、`file_isolation=off`、`file_root=/data` 后保存
- **THEN** SPA 调 `POST /admin/mcp/servers` 带这 3 个字段,`GET /admin/mcp/servers` 该 server 记录回显它们

#### Scenario: 物化服务级字段到托管 agent 的 agent.yaml

- **WHEN** 一个配了非默认 `degrade_mode`/`file_isolation`/`file_root` 的 MCP server 被物化进某托管 agent 的 `agent.yaml`
- **THEN** 该 server 的 `mcpServers.<id>.x-fleetent` 下出现这些非默认字段,全默认字段不出现

#### Scenario: 非法枚举值被拒绝

- **WHEN** 请求体携带不在枚举内的 `degrade_mode` 或 `file_isolation`
- **THEN** 响应为 422,不写入 store

#### Scenario: 服务表单不含审批规则

- **WHEN** 管理员打开 MCP server 新建/编辑表单
- **THEN** 表单不出现审批规则(`approval_rules`)编辑器,`POST/PUT /admin/mcp/servers` 也不接受 `approval_rules` 字段(审批规则改在 agent 绑定处配置)
