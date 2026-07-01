## Why

MCP server 新建/编辑表单(`features/mcp/page.tsx`)字段很多,且鉴权类型不同会显示不同字段集。管理员填表时不知道每个输入框最终对应 `agent.yaml` 里的哪个字段路径(哪些是顶层字段、哪些会被提到 `mcpServers.<id>.x-fleetent.auth.*` 下),排查/核对配置时只能去翻后端代码。

## What Changes

- 后端 `materialize.py` 新增纯函数 `mcp_yaml_field_paths()`:直接遍历 `McpServerSettings.model_fields` + 复用既有的 `_FLEETENT_EXT_DEFAULTS`(判断哪些字段要提到 `x-fleetent` 下)+ `McpOAuthSettings.model_fields`(展开 `auth.*` 子字段),产出 `{字段名: "mcpServers.{id}.xxx"}` 路径模板表。不新增手写映射——这份函数直接读现有的整形逻辑,不可能和 `_mcp_payload_to_map` 的真实写盘行为漂移(该函数同时被 standalone 物化和 node 托管 `desired_state` 同步复用)。
- `connector_admin_api.py` 新增只读端点 `GET /admin/mcp/field-schema`,鉴权对齐既有 `GET /admin/mcp/servers`(任意已登录用户,`_current_user`,无需 admin 角色),返回上述路径表。
- 前端 `features/connectors/api.ts` 新增 `useMcpFieldSchemaQuery()`(`staleTime: Infinity`);`features/mcp/page.tsx` 的新建/编辑表单里,每个字段下方用现有的 `text-xs text-muted-foreground` 小字样式常驻展示对应 `agent.yaml` 路径,路径模板里的 `{id}` 替换为当前 ID 输入框的实际值(未填时回退为 `<id>`)。`id`/`作用域` 两个字段不对应 `McpServerSettings` 的字段(分别是 map key 和路由到哪个 agent 的 DB 列),继续手写说明文案。

## Capabilities

### New Capabilities

(无)

### Modified Capabilities

- `mcp-server-admin`:新增"表单字段常驻展示对应 agent.yaml 路径"——此前表单只展示中文标签,不展示字段和 `agent.yaml`/`x-fleetent` 结构的映射关系。

## Impact

- **新增**:`connector_admin_api.py` 的 `GET /admin/mcp/field-schema` 端点;`materialize.py` 的 `mcp_yaml_field_paths()` 纯函数。
- **改动**:`frontend/src/features/connectors/api.ts`(新增 query hook)、`frontend/src/features/mcp/page.tsx`(渲染路径小字提示)、`frontend/src/i18n/messages.ts`(补 `id`/作用域两条说明文案的 en + zh)。
- **边界**:纯只读展示功能,不改任何写入路径(建/改/删 MCP server 的行为不变),不改 `agent.yaml` 实际内容或 `_mcp_payload_to_map` 的整形逻辑。
