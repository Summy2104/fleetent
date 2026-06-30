## 1. 后端归一化持久化 token_env

- [x] 1.1 写 unit 测试：`_normalized_auth_config('oauth_authorization_code', {...含 token_env})` 返回含 `token_env`；不填 token_env 时为空字符串且其它字段不变（见红）
- [x] 1.2 实现：`connector_admin_api._normalized_auth_config` 的 `OAuthAuthorizationCodeMcpAuthConfig` 分支加 `"token_env": parsed.token_env`（见绿）

## 2. 前端表单 token_env

- [x] 2.1 写 page.test 用例：选择「OAuth 授权码（按用户动态授权）」并填 token_env，提交后 payload.auth_config 含 token_env；token_env 留空仍可创建（见红）
- [x] 2.2 实现：`connectors/api.ts` 的 `McpOAuthAuthorizationCodeAuthConfig` 加 `token_env`；`AUTH_CONFIG_FIELDS.oauth_authorization_code` 加 `token_env`（见绿）
- [x] 2.3 实现：`mcp/page.tsx` 加 oauthTokenEnv 状态、编辑回填、提交分支带 token_env、oauth_authorization_code 字段组渲染可选 token_env 输入；`i18n/messages.ts` 中英文文案（见绿）

## 3. 收尾验证

- [x] 3.1 后端最窄层：`uv run pytest` 跑 1.x 测试全绿
- [x] 3.2 前端：`tsc` + `eslint` + `vitest`（page.test）相关用例全绿
- [x] 3.3 change 收尾：`make test-pr` + 前端门禁全绿（仅已知本地假失败）
