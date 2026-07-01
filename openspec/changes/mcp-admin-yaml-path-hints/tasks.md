> TDD 硬门禁:每个实现 task 先写测试见红,再写实现见绿,不可跳步。后端最窄命令 `uv run pytest <file>::<test> -x -q`;前端最窄命令 `yarn --cwd frontend vitest run <file>`。

## 1. 后端:路径表纯函数(unit,TDD)

- [ ] 1.1 写测试 `tests/unit/platform/agent_lifecycle/test_materialize_mcp_field_paths.py`:覆盖 D1 表格里的关键路径断言——`auth_type`/`api_key_env`/`header_style`/`credential_input` **不**带 `x-fleetent` 前缀;`auth.client_id` 等 7 个 OAuth 子字段**带** `mcpServers.{id}.x-fleetent.auth.` 前缀;返回值不包含 `id`/`connect_timeout`/`call_timeout` 这 3 个 key。先见红(函数不存在)。
- [ ] 1.2 在 `materialize.py` 实现 `mcp_yaml_field_paths()`(design.md D1 给出的实现),紧邻 `_FLEETENT_EXT_DEFAULTS` 定义处。跑 1.1 见绿。

## 2. 后端:只读端点(integration,TDD)

- [ ] 2.1 写测试(`tests/integration/platform/connector_management/...`,复用现有 `/admin/mcp/servers` 测试的 fixture 风格):已登录任意角色请求 `GET /admin/mcp/field-schema` 返回 200 且内容等于 `mcp_yaml_field_paths()`;未带登录会话返回 401。先见红。
- [ ] 2.2 在 `connector_admin_api.py` 新增该端点(鉴权用 `_current_user`,不要求 admin 角色,对齐 `list_mcp_servers`)。跑 2.1 见绿。

## 3. 前端数据层(api.ts,TDD)

- [ ] 3.1 写测试(Vitest + MSW):`useMcpFieldSchemaQuery` 命中 `GET /admin/mcp/field-schema`,返回体原样透出。先见红。
- [ ] 3.2 在 `features/connectors/api.ts` 实现该 hook(`staleTime: Infinity`,风格照现有 `useMcpServersQuery`)。跑 3.1 见绿。

## 4. 前端表单渲染(page.tsx,TDD)

- [ ] 4.1 写测试(`page.test.tsx`,mock `useMcpFieldSchemaQuery` 返回值):
  - `transport`/`command`/`url`/`args`/`env`/`headers` 等常规字段下方渲染 `mcpServers.<当前id>.<字段>`
  - 切换 `authType` 为 `oauth_client_credentials` 后,Token URL/Client ID 等字段下方渲染 `mcpServers.<id>.x-fleetent.auth.<子字段>`,且鉴权类型下拉本身对应字段(`auth_type`,不带 `x-fleetent`)与其他鉴权类型字段的提示不冲突
  - ID 输入框填入 `demo` 后,其余提示的占位符替换为 `demo`;清空后回退显示 `<id>`
  - `id` 输入框和"作用域"选择器下方展示手写说明文案(不依赖 mock 的 schema 返回值)
  先见红。
- [ ] 4.2 在 `mcp/page.tsx` 实现:引入 `useMcpFieldSchemaQuery()`、`fieldPath(schema, key, id)` helper、每个字段块下方补 `<p className="text-xs text-muted-foreground font-mono">`;`i18n/messages.ts` 补 `mcp.idYamlHint` / `mcp.scopeYamlHint` 的 en + zh 词条(en 权威源,zh 类型强制对齐)。跑 4.1 见绿。

## 5. Change 收尾验证

- [ ] 5.1 `make test-pr` + `make test-integration-ci` 全绿(无新增失败)。
- [ ] 5.2 `make test-frontend` 全绿(vitest + 覆盖率阈值 + tsc --noEmit + lint)。
- [ ] 5.3 手动核对:本地起 platform + vite dev server,实际打开 MCP 新建表单,切换传输方式/鉴权类型、填写 ID,确认每个字段下方的路径提示符合预期且随输入实时更新。
