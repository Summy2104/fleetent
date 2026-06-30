## 1. 跳过 auth_type 的 inline-secret 扫描

- [ ] 1.1 写 unit 测试：构造一个含 `auth`(McpOAuthSettings, grant=authorization_code) + 顶层 `auth_type='oauth_authorization_code'` 的 MCP server 的 AgentFile，调 `_reject_inline_secrets` **不抛**（见红：当前会因 auth_type 抛 ValueError）；并保留一个对照断言——某非 `*_env` 字段内联明文密钥仍抛（守卫未被削弱）
- [ ] 1.2 实现：`agent_config._SKIP_SECRET_SCAN_SEGMENTS` 增加 `.auth_type`（见绿）

## 2. 收尾验证

- [ ] 2.1 最窄层：`uv run pytest <test> -x -q` 见绿
- [ ] 2.2 change 收尾：`make test-pr` 全绿（仅已知本地假失败）
