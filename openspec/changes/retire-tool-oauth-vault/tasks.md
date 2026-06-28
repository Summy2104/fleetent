## 1. seam 安全降级（守住验证基线 · 测试先行）

- [ ] 1.1 写测试：未注入 provider 时 `connectors.get_credential(...)` 经 `_default_provider` 返回 `NeedsConsent`，不抛错（`tests/unit`，对 `connectors.py` seam）
- [ ] 1.2 写测试：声明 `@tool(connector="github")` 的工具在无 provider 时 dispatch 优雅短路返回 consent、agent 循环不中断（`tests/unit`，对 `tools/registry.py` 通道）
- [ ] 1.3 写测试：无 platform、管理库表不存在环境下 `fleetent agent run` 可完成对话、凭证类工具降级 NeedsConsent（`tests/integration`，无-platform 基线）
- [ ] 1.4 跑上述测试确认通过当前代码（seam 本就保留，应绿）——确立"不可回归"基线；若有红先修测试假设

## 2. Alembic 迁移 108（drop 三表 · 测试先行）

- [ ] 2.1 写迁移测试：升级到 108 后 `external_services` / `external_credentials` / `agent_service_grants` 不存在；`agents` 删除路径仍仅 `DELETE FROM agents` 且不再触达已删表（`tests/integration`，见红）
- [ ] 2.2 实现迁移 `108_retire_tool_oauth_vault.py`：按 `agent_service_grants` → `external_credentials` → `external_services` 顺序 drop（forward-only）→ 跑 2.1 见绿

## 3. platform 侧实现移除（store / provider / API）

- [ ] 3.1 写测试：`/admin/connectors`、`/admin/connectors/grants`、OAuth 授权/回调、`/admin/agents/{name}/bindings/oauth*` 端点不再注册（请求得 404/路由不存在）（`tests/integration`，见红）
- [ ] 3.2 删 `external_service_store.py` / `external_credential_store.py` / `agent_service_grant_store.py`（含 `agent_oauth_binding_store` re-export shim）
- [ ] 3.3 删 `vault_provider.py`
- [ ] 3.4 删 `connector_admin_api.py` 的 connector 目录/grants/consent/吊销端点；删 `agent_admin_api.py` 的 oauth 绑定端点（约 509-560）→ 跑 3.1 见绿
- [ ] 3.5 仅清 vault grant 维度的 `run_as` 解析；**不动** sandbox `run_as`、`agent_config.py` `run_as`、`agent-service-principal` 铸造机制

## 4. server.py 解注入与 hook 移除

- [ ] 4.1 写测试：应用启动后 `connectors._provider` 为 `_default_provider`（未被 vault 注入）；`delete_agent` 路径无对 `external_credential_store` 的调用（`tests/integration`，见红）
- [ ] 4.2 删 `server.py` 的 `connectors.set_provider(vault_provider...)` 注入与 delete-agent 清凭证 hook → 跑 4.1 见绿
- [ ] 4.3 server 启动冒烟：无残留 import、应用可正常 lifespan 启动

## 5. 前端 OAuth 面移除（精确摘除，保留 MCP）

- [ ] 5.1 写/改前端测试：agent 详情页无 OAuth tab、`features/agents/api.ts` 不再导出 OAuth hooks；`McpServerRecord` 及 MCP servers view 仍在（`frontend` vitest，见红）
- [ ] 5.2 删 `features/connectors/` 的外部服务/grants 部分、`features/agents/api.ts` 的悬空 OAuth hooks、OAuth Connectors tab、`/connectors` 路由与 i18n；按符号精确摘除，保留 `connectors/api.ts` 内 MCP 类型 → 跑 5.1 见绿

## 6. 残留清理与守卫

- [ ] 6.1 全仓 grep `external_service_store` / `external_credential_store` / `agent_service_grant_store` / `agent_oauth_binding_store` / `vault_provider` 残留引用归零（含测试与 fixtures）
- [ ] 6.2 同步删/改受影响的既有 guard / 端点测试（按 memory `fleetent-ci-timebomb-tests` 教训核查 integration 层，避免"PR 绿 main 红"）
- [ ] 6.3 确认未踩 change ② 地盘：未改 `mcp_servers` 表、未改 `materialize.py` 的 MCP/model 函数

## 7. 收尾验证

- [ ] 7.1 跑 `make test-pr` + `make test-integration-ci` 全绿（无新增失败）
- [ ] 7.2 跑前端测试套件全绿
- [ ] 7.3 无-platform `fleetent agent run` 手动冒烟，确认凭证类工具降级、对话完成（验证基线）
