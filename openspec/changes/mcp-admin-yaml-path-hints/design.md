## Context

`materialize.py` 的 `_mcp_payload_to_map()` + `_FLEETENT_EXT_DEFAULTS` 是 `McpServerSettings` → `agent.yaml` 的 `mcpServers.<id>` 结构唯一整形逻辑,被 `desired_state_payload_from_agent_file()` 调用——这条路径同时服务 standalone 物化(`materialize_agent_home`)和 node 托管同步(`node_desired_state_api.py` 调 `materialize.desired_state_payload_from_agent_file`),没有第二份拷贝。前端 `features/mcp/page.tsx` 的表单字段和这份整形逻辑是手工对应的(字段名基本一致),但表单上完全不展示这层映射关系。

## Goals / Non-Goals

**Goals:** 管理员在填写/查看 MCP server 表单时,每个字段下方能看到它最终落在 `agent.yaml` 的哪个路径,尤其是"哪些字段会被提到 `x-fleetent` 下"这个不直观的部分。路径数据只能有一份来源,不能在前端另开一张手写表。

**Non-Goals:** 不改 `_mcp_payload_to_map` / `_FLEETENT_EXT_DEFAULTS` 本身的整形行为;不做"整份 agent.yaml 实时预览"(信息量更大但改动面也更大,本次先做逐字段小字提示,验证需求后再考虑);不覆盖 `degrade_mode`/`file_root`/`file_isolation`/`approval_rules`/`connect_timeout`/`call_timeout` 的提示(表单当前没有这些字段的输入框,`mcp_yaml_field_paths()` 会算出它们的路径但前端不渲染,不属于本次范围)。

## Decisions

**D1 · 路径表从 `materialize.py` 派生,不在前端手写。**
新增 `mcp_yaml_field_paths() -> dict[str, str]`,逻辑:

```python
def mcp_yaml_field_paths() -> dict[str, str]:
    paths: dict[str, str] = {}
    for name in McpServerSettings.model_fields:
        if name in ("id", "connect_timeout", "call_timeout"):
            continue
        if name == "auth":
            for sub in McpOAuthSettings.model_fields:
                paths[f"auth.{sub}"] = f"mcpServers.{{id}}.x-fleetent.auth.{sub}"
        elif name in _FLEETENT_EXT_DEFAULTS:
            paths[name] = f"mcpServers.{{id}}.x-fleetent.{name}"
        else:
            paths[name] = f"mcpServers.{{id}}.{name}"
    return paths
```

跳过 `id`(是 map key,不是字段值)和 `connect_timeout`/`call_timeout`(表单没有对应输入框,产出了也用不上,保留最小输出)。`auth` 字段本身不产出 `x-fleetent.auth` 这一条,只展开子字段——因为表单里没有"整个 auth 对象"这个输入框,只有 `token_url`/`client_id` 等子字段输入框。

理由:这份表和 `_mcp_payload_to_map` 读的是同一个 `_FLEETENT_EXT_DEFAULTS`,任何人改了哪些字段该提到 `x-fleetent` 下,这份路径表会跟着变,不会漂移。

验证过的关键路径(与当前代码行为核对一致):
| 字段名 | 路径 |
|---|---|
| `transport` | `mcpServers.{id}.transport` |
| `command` | `mcpServers.{id}.command` |
| `url` | `mcpServers.{id}.url` |
| `args` | `mcpServers.{id}.args` |
| `env` | `mcpServers.{id}.env` |
| `headers` | `mcpServers.{id}.headers` |
| `auth_type` | `mcpServers.{id}.auth_type`(**不在** `x-fleetent` 下,是顶层字段) |
| `api_key_env` | `mcpServers.{id}.api_key_env`(顶层) |
| `header_style` | `mcpServers.{id}.header_style`(顶层) |
| `credential_input` | `mcpServers.{id}.credential_input`(顶层) |
| `auth.token_url` / `auth.client_id` / `auth.client_secret_env` / `auth.scope` / `auth.authorization_endpoint` / `auth.redirect_path` / `auth.token_env` | `mcpServers.{id}.x-fleetent.auth.<sub>` |

**D2 · 新增独立只读端点,不塞进现有 `GET /admin/mcp/servers` 响应。**
这份 schema 是纯代码派生的静态数据,不依赖任何具体 server 实例,和"服务器列表"是两种不同生命周期的数据(列表随时变,schema 只随代码变)。塞进每条 server 记录里会重复且无意义。独立端点 `GET /admin/mcp/field-schema` 语义更清晰,前端可以用更长的 `staleTime` 单独缓存。鉴权对齐 `GET /admin/mcp/servers`(`_current_user`,不要求 admin 角色)——这不是敏感信息,viewer 也该能看到字段说明。

**D3 · `id` 和"作用域"两个字段不来自 schema,前端手写说明。**
`id` 是 `mcpServers` map 的 key,不是某个字段的值,展示"作为 `mcpServers` 下的键名"这类说明。"作用域"选择器对应的是 `mcp_servers` 表的 `agent_id` 列(决定这条配置写入哪个 agent 的 `agent.yaml`,或作为全局默认),根本不是 `McpServerSettings` 的字段,不会出现在某一份 `agent.yaml` 内容里。这两条不需要"跟代码同步",因为它们描述的是路由/寻址关系,不是字段整形关系,写死两句 i18n 文案即可。

**D4 · `{id}` 占位符替换为表单里实时输入的 ID。**
`fieldPath(schema, key, id)` = `schema[key].replace('{id}', id.trim() || '<id>')`,随 ID 输入框实时更新——已与用户确认,所见即所得优先于实现简单性。

## Risks / Trade-offs

- **[`mcp_yaml_field_paths()` 仍需人工维护 `connect_timeout`/`call_timeout` 的跳过名单]** → 影响面很小(只有 2 个字段,且表单本来就没有它们的输入框),后续如果表单加了这两个字段的输入框,直接把它们从跳过名单删掉即可,不需要新逻辑。
- **[前端字段 key 和后端 `mcp_yaml_field_paths()` 的 key 命名要对齐]** → 前端渲染时用字符串 key(如 `'auth.client_id'`)去查 schema 返回的 dict,如果两边字段名拼错会静默拿不到提示(不会报错,只是那个字段下面不显示提示文字)。用组件测试覆盖每个已知字段 key 能查到非空路径来兜底。
