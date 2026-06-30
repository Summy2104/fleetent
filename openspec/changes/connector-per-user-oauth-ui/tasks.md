## 1. 后端 connector 落库归一化（oauth_authorization_code）

- [x] 1.1 写 unit 测试：`_normalized_auth_config('oauth_authorization_code', {...})` 持久化 authorization_endpoint / token_url / client_id / client_secret_env / scope / redirect_path，且不为空对象（见红）
- [x] 1.2 写 unit 测试：`McpServerCreateBody` 以 `auth_type=oauth_authorization_code` 构造时归一化保留上述字段；缺必填（authorization_endpoint/token_url/client_id）经 `parse_mcp_auth_config` 校验被拒（见红）
- [x] 1.3 实现：`connector_admin_api._normalized_auth_config` 新增 `OAuthAuthorizationCodeMcpAuthConfig` 分支，列出持久化字段（见绿）

## 2. managed 授权链接投递 fallback（outbound）

- [x] 2.1 写 unit 测试：`make_mcp_authz_deliverer` 在 node-managed 运行时（无 live connector）经 `outbound_connectors.notify_user` 投递并返回 True（见红）
- [x] 2.2 写 unit 测试：standalone（有 live connector）仍走既有 `send_to`；既非 connector 又非 managed 时返回 False 且不抛异常（见红/守护既有行为）
- [x] 2.3 实现：`outbound.make_mcp_authz_deliverer` 补 `is_node_managed_runtime() → notify_user` fallback 分支，与 `make_mcp_credential_deliverer` 对称（见绿）

## 3. 前端 connector 表单（oauth_authorization_code）

- [x] 3.1 写 page.test 用例：选择「OAuth 授权码（按用户动态授权）」后渲染 authorization_endpoint / token_url / client_id / client_secret_env / scope / redirect_path 字段（见红）
- [x] 3.2 写 page.test 用例：填齐必填后提交，断言 payload `auth_type=oauth_authorization_code` 且 auth_config 含已填字段；缺必填时提交按钮禁用（见红）
- [x] 3.3 实现：`connectors/api.ts` 的 `McpAuthType` 加 `oauth_authorization_code`，`AUTH_CONFIG_FIELDS` 加其字段列；`mcp/page.tsx` 下拉新增项 + 字段组渲染 + 提交分支 + 可创建校验；`i18n/messages.ts` 中英文文案（见绿）

## 4. 收尾验证

- [x] 4.1 后端最窄层：`uv run pytest` 跑 1.x/2.x 相关测试文件全绿
- [x] 4.2 前端：`npm --prefix frontend run lint` + `tsc` + `vitest` 相关用例全绿
- [x] 4.3 change 收尾：`make test-pr` 与前端门禁全绿（无新增失败）
