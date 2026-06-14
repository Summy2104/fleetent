# Tasks — connector-admin-wiring（P5）

> 依赖 P0、建议 P2 之后 apply。TDD：测试任务前置。触及 DB/FastAPI 的测试放 integration。

## 1. 授权矩阵接 Vault

- [ ] 1.1 写测试（integration）：`connectors_list_grants` 从 external_credentials.status 产出 `(user, service)` 矩阵（authorized/not_authorized/needs_reauth/error），无 owning-agent 维度；按 user / 按 service 两视角聚合一致。
- [ ] 1.2 实现：`connectors_list_grants` 接 Vault（替换 placeholder `[]`）。运行 1.1 见绿。

## 2. admin 吊销接 Vault

- [ ] 2.1 写测试（integration）：admin revoke `(user, service)` → 触发 Vault revoke、需确认、落审计；吊销后矩阵该格回 not_authorized；viewer 被 403。
- [ ] 2.2 实现：`connectors_revoke` 接 P2 revoke。运行 2.1 见绿。

## 3. offboarding 联动可见性

- [ ] 3.1 写测试（integration）：用户停用 → Vault 自动吊销其全部凭证 → `connectors_offboarding_result` 展示各服务成功/失败。
- [ ] 3.2 实现：停用联动 + `connectors_offboarding_result` 接 Vault。运行 3.1 见绿。

## 4. 生命周期可观测

- [ ] 4.1 写测试（integration）：`connector_lifecycle_stats` 返回每服务刷新成功/失败率与重新授权次数（数据源自 P2）。
- [ ] 4.2 实现：`connector_lifecycle_stats` 接 Vault token-lifecycle 数据。运行 4.1 见绿。

## 5. 收尾

- [ ] 5.1 全视图遮蔽校验：client_secret / access / refresh token 在矩阵、lifecycle、审计中均遮蔽。
- [ ] 5.2 `make test-pr` 全绿；`uv run pytest tests/integration -q` 无新增失败。
