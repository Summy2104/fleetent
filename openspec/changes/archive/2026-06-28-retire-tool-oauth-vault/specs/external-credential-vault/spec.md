## REMOVED Requirements

> **共同 Reason**：整套工具 OAuth Vault 是 build-but-unwired 半成品——零生产工具消费（唯一 `@tool(connector=)` 为测试工具），前端 OAuth tab 从未渲染。团队决定工具凭证鉴权挪到 agent 侧实现，平台退役本能力。
> **共同 Migration**：drop `external_services` / `external_credentials` 表（Alembic 108）；删 legacy service store / credential store / 平台 provider。agent 侧 `connectors.py` seam 保留（见 `connector-credential-injection`）；解除 platform 注入后 `get_credential` 经 `_default_provider` 安全降级为 `NeedsConsent`。将来 agent 侧自行实现并 `set_provider`。

### Requirement: 外部服务注册表（单层全局，多协议）
**Reason**: 退役工具 OAuth Vault（半成品，零工具消费）。
**Migration**: drop `external_services`；服务定义改由 agent 侧承载。

### Requirement: per-principal 加密凭证存储
**Reason**: 退役工具 OAuth Vault。
**Migration**: drop `external_credentials`；per-principal 凭证改由 agent 侧实现。

### Requirement: 加密复用既有 Fernet 主密钥
**Reason**: 随 `external_credentials` 退役，平台不再加密存储工具凭证。
**Migration**: 主密钥仍服务其它密文用途（如 `agent_secrets`）；本能力的凭证加密路径删除。

### Requirement: Vault provider 经 seam 注入并按 principal 解析
**Reason**: 退役 platform 侧 vault provider 实现。
**Migration**: 删平台 provider；`server.py` 不再 `set_provider`，seam 回落 `_default_provider`（`NeedsConsent`）。

### Requirement: 最小 OAuth2 授权码 consent 流
**Reason**: 退役 platform 侧 OAuth consent 流。
**Migration**: 删授权/回调端点；OAuth consent 改由 agent 侧实现。

### Requirement: access token 过期自动刷新
**Reason**: 随 vault provider 退役。
**Migration**: token 刷新逻辑随平台 provider 删除。

### Requirement: refresh 失效与错误的状态流转
**Reason**: 随 `external_credentials` 状态机退役。
**Migration**: 凭证状态流转随表删除。

### Requirement: 凭证吊销
**Reason**: 随 `external_credentials` 退役。
**Migration**: 删 `/admin/connectors/grants` 吊销路径；凭证吊销改由 agent 侧实现。

### Requirement: 用户提交 API key 凭证
**Reason**: 退役工具 OAuth Vault 的 API-key 录入路径。
**Migration**: 删提交端点；API-key 凭证改由 agent 侧实现。

### Requirement: API-key 凭证解析
**Reason**: 随 vault provider 退役。
**Migration**: API-key 解析随平台 provider 删除。

### Requirement: provider 适配层支持多服务
**Reason**: 随平台 provider 退役。
**Migration**: 多服务适配随 provider 实现删除；agent 侧将来按需实现。

### Requirement: 禁用的外部服务在凭证解析被门控
**Reason**: 随 `external_services.enabled` 门控退役。
**Migration**: `enabled` 门控随表删除。
