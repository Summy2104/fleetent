## Why

P0 只打通 OAuth2 授权码协议。但很多外部服务（含非 OAuth 的 MCP server）用 **API key** 鉴权——用户需要把自己的外部服务 API key 交给平台、平台加密代存，调用时按用户身份注入（Case 2b）。本变更补齐 `protocol=api_key` 的凭证路径：用户提交 key → 加密入 `external_credentials` → dispatch 时解析为 `Credential`。

> Apply 顺序：依赖 `external-credential-vault`（P0）先 archive；与 P2（OAuth 生命周期）无耦合，可并行。

## What Changes

- **用户提交 API key 流**：为 `protocol=api_key` 的服务提供「用户提交自己的 API key」入口（用户本人提交，admin 不能代填），key 经 Fernet 加密写入 `external_credentials`，`status=authorized`。
- **API-key 凭证解析**：Vault provider 对 `protocol=api_key` 的服务解析出 `Credential`（client 携带该用户的 key）；无 key 时返回 `NeedsConsent`（提示用户去提交 key，而非 OAuth 跳转）。
- **API key 无 refresh 概念**：不参与 P2 的刷新流；失效时由用户重新提交。
- key 明文 MUST NOT 进日志 / trace / 异常 / 返回值。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `external-credential-vault`: 新增 API-key 协议的凭证提交与解析要求（ADDED 扩展 vault；`external_credentials` 密文负载支持 `api_key{value}` 形态，P0 已预留）。

## Impact

- **owning package**：`platform/connector_management`（API-key 提交端点 + provider 的 api_key 解析分支）。
- **public API surface**：新增「用户提交 API key」端点（platform 控制面，用户自助）；`get_credential` 对 api_key 服务返回 `Credential`/`NeedsConsent`——契约形状不变。
- **owned tables**：无新增（复用 `external_credentials`，密文存 `api_key{value}`）。
- **config namespace**：无（复用 `FLEETENT_SECRET_KEY`）。
- **cross-module dependencies**：纯 platform；agent runtime 仅经 seam 只读；不碰 agent⊥platform。
- **migration / shim plan**：无 schema 迁移。
- **不在范围**：把 MCP server 的 per-user api_key 接进来（MCP auth 现为服务级 env，迁移到 per-user vault 属后续专项，本变更只覆盖工具 connector 路径）；OAuth 刷新（P2）。
