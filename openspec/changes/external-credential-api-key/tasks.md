# Tasks — external-credential-api-key（P3）

> 依赖 P0 已 archive。TDD：测试任务前置。触及 DB/FastAPI 的测试放 integration。

## 1. 用户提交 API key 流

- [ ] 1.1 写测试（integration）：用户为 api_key 服务提交 key → 加密入 external_credentials（密文非明文）→ status=authorized；明文不回显；无「管理员代填」端点。
- [ ] 1.2 实现：用户自助提交端点（复用 session auth），加密复用 P0 crypto helper。运行 1.1 见绿。

## 2. API-key 凭证解析

- [ ] 2.1 写测试（integration）：有 key → provider 返回携带 key 的 Credential，dispatch 注入隐藏 client 执行；无 key → NeedsConsent 提示指向提交入口；不触发刷新。
- [ ] 2.2 写测试（integration）：key 明文不进返回值 / trace / 异常。
- [ ] 2.3 实现：provider 的 api_key 解析分支。运行 2.1–2.2 见绿。

## 3. 收尾

- [ ] 3.1 `make test-pr` 全绿；`uv run pytest tests/integration -q` 无新增失败。
