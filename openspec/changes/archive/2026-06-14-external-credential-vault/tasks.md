# Tasks — external-credential-vault（首切片 / tracer bullet）

> TDD 硬门禁：每个实现任务前先写测试并见红，再实现见绿。测试任务一律排在对应实现任务之前。
> 触及真实 DB / schema / CRUD / Alembic 的测试放 `tests/integration/`；纯函数（crypto helper）放 `tests/unit/`。
> 迁移号不写死：接当前 head 顺延。

## 1. Schema 迁移（重命名 + 新建表）

- [x] 1.1 写迁移测试（integration）：升级到 head 后 `external_services` 存在且**无** `agent_id` 列与 `ux_connectors_agent_scope` / `ux_connectors_global_scope` 索引；旧 `connectors` 表不存在；存量行迁移保留。
- [x] 1.2 写迁移测试（integration）：`agent_oauth_bindings` 被重命名为 `agent_service_grants`，含 `run_as` 列（默认 `user`）与 `(agent_id, service_id)` 主键，保留 `FK agent_id→agents.id ON DELETE CASCADE`，存量行保留。
- [x] 1.3 写迁移测试（integration）：`external_credentials` 表存在，主键 `(user_id, service_id)`，含密文列与 `status` 列。
- [x] 1.4 写迁移测试（integration）：`delete_agent` 删除 agent 后 `agent_service_grants` 中其绑定经 CASCADE 清零（无孤儿）。
- [x] 1.5 实现迁移：`connectors`→`external_services`（建新表去 `agent_id` 列+两 partial 索引、迁数据、改名，SQLite 模式对照迁移 085）；`agent_oauth_bindings`→`agent_service_grants`（加 `run_as` 默认 `user`、保 CASCADE）；新建 `external_credentials`。downgrade 反向。运行 1.1–1.4 见绿。

## 2. 共享 Fernet crypto helper

- [x] 2.1 写测试（unit，纯函数）：crypto helper 用 `FLEETENT_SECRET_KEY` 加密→解密往返一致；缺/坏 key 抛清晰错误；密文 ≠ 明文。
- [x] 2.2 实现：从 `secret_store.py` 抽出可共享的 `_fernet()` / encrypt / decrypt helper（`secret_store` 改为复用之，行为不变）。运行 2.1 见绿，并确认既有 `agent_secrets` 测试不回归。

## 3. external_services 注册表 store

- [x] 3.1 写测试（integration）：`add_service` / `get_service` / `list_services`（单层全局，无 agent 维度）；同 `service_id` 重复注册被拒；`client_secret` 永不入库。
- [x] 3.2 实现：`external_services` store（重塑自 `connector_config_store`，去 overlay/agent_id 分支，named params 经 db 边界）；`connector_config_store` 模块路径留 re-export shim。运行 3.1 见绿。
- [x] 3.3 实现：`agent_oauth_binding_store` 重命名为 grant store（`bind/unbind/list_services_for_agent/list_agents_for_service`，service_id 命名），旧路径留 re-export shim。补 store 重命名的 integration 测试并见绿。

## 4. external_credentials 凭证 store（加密）

- [x] 4.1 写测试（integration）：写入 `(user_id, service_id)` OAuth token → 落盘列为密文、读取解密一致、`status=authorized`；按 principal 隔离（u2 读不到 u1）；缺 `FLEETENT_SECRET_KEY` 时写/读抛错不落明文。
- [x] 4.2 实现：`external_credentials` store（复用 §2 crypto helper，named params，明文不入返回/日志/审计）。运行 4.1 见绿。

## 5. Vault provider + seam 接线

- [x] 5.1 写测试（integration）：Vault provider 实现 `CredentialProvider`，对已授权 `(user, service)` 返回 `Credential`，未授权 / `user_id` 缺失返回 `NeedsConsent`。
- [x] 5.2 写测试（integration）：platform 启动接线后 `connectors.get_credential` 经注入的 Vault provider 解析；未注入（standalone）时 seam 仍恒 `NeedsConsent`，且无 `import fleetent.platform.*`（module-boundary 护栏）。
- [x] 5.3 实现：Vault provider；platform 启动处 `connectors.set_provider(vault_provider)`（对标 `set_api_key_resolver` 接线点）。运行 5.1–5.2 见绿。
- [x] 5.4 运行 `scripts/check_module_boundaries.py` 与依赖护栏，确认 agent runtime 未新增对 platform 的反向 import。

## 6. 最小 OAuth2 授权码 consent 流

- [x] 6.1 写测试（integration）：authorize 端点返回带 `state` 的授权 URL；callback 端点 `state` 通过时以 code 换 token（外部 HTTP 用 `respx`/mock）→ 加密写入 `external_credentials` → `status=authorized`；`state` 不匹配则不换 token、不写入。
- [x] 6.2 写测试（integration）：不存在任何「管理员代用户完成首次 consent」的端点（沿用旧 guard）。
- [x] 6.3 实现：consent 流的 authorize / callback 端点（platform 控制面，复用既有 session auth guard）。运行 6.1–6.2 见绿。

## 7. 端到端真工具验证

- [x] 7.1 写测试（unit）：一个 builtin 工具以 `@tool(connector="<service>")` 注册，connector 元数据可查且不进 LLM schema（复用既有 injection 契约，provider 用 mock）。
- [x] 7.2 写测试（integration，e2e 纵切）：已授权用户调用该工具 → Vault provider 解析真实 per-user 凭证 → dispatch 注入隐藏 `client` → 工具执行返回结果；未授权用户 → 短路返回 consent 提示；凭证 secret 不进返回值 / trace。
- [x] 7.3 实现：新增一个真实 builtin 工具声明 `@tool(connector=...)`（最小可执行，证明端到端取到 per-user 凭证）。运行 7.1–7.2 见绿。

## 8. 收尾校验

- [ ] 8.1 `make test-pr` 全绿（unit + 层边界 + 改动文件 ruff）。
- [ ] 8.2 `uv run pytest tests/integration -q` 对照 main 基线无新增失败。
- [ ] 8.3 复核：re-export shim 使仅文字引用旧表名/旧 store 路径的代码与运行路径不破；`data-model.md` 与主 specs 未被本切片改动。
