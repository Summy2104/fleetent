# Tasks — oauth-token-lifecycle（P2）

> 依赖 P0 已 archive。TDD：测试任务前置。外部 HTTP 用 respx mock。触及 DB 的测试放 integration。

## 1. token 过期自动刷新

- [ ] 1.1 写测试（integration）：现有 payload 仅含 `access_token` / `refresh_token` / provider token 响应字段时，access token 过期 + refresh 有效 → 解析触发刷新（respx mock `oauth_config.token`）→ 在密文 payload 内回写新 token 与标准化 `expires_at` → 返回有效 Credential；未过期不发刷新请求。
- [ ] 1.2 写测试（integration）：刷新过程中 token 明文不进 trace / 日志 / 异常文本。
- [ ] 1.3 实现：Vault provider 解析时的过期检测 + 刷新 + 回写；基于真实 `external_credential_store.put_oauth_credential/get_credential` 签名工作，不加新表/新列。运行 1.1–1.2 见绿。

## 2. 状态流转

- [ ] 2.1 写测试（integration）：refresh token 失效 → status=needs_reauth → 解析返回 NeedsConsent；刷新网络失败 → status=error → 解析返回新的 retryable credential error（区别于未授权）。
- [ ] 2.2 实现：状态流转逻辑与 status 列更新；必要时扩 `connectors.py` seam 以表达 retryable credential error。运行 2.1 见绿。

## 3. 凭证吊销

- [ ] 3.1 写测试（integration）：revoke 删除本地凭证 + 尽力调外部 revoke（respx）；外部失败仅记日志、本地仍删除；吊销后解析返回 NeedsConsent。
- [ ] 3.2 实现：在真实 `external_credential_store` 上补 revoke/delete 能力 + provider revoke 调用（舱壁化）。运行 3.1 见绿。

## 4. 收尾

- [ ] 4.1 `make test-pr` 全绿；`uv run pytest tests/integration -q` 无新增失败。
