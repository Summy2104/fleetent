## Why

per-user OAuth (`mcp-per-user-oauth2` 切片 1/2) 让用户以各自身份访问同一 MCP server，但只覆盖 OAuth2.1 authorization_code。许多 MCP server 用的是**静态 api-key / bearer token**——而 fleetent 当前的 api_key 鉴权是 **per-server 静态**（`key_env` 从 `.env` 读，全用户共享一把机器 key），无法做到"每个用户用自己的 api-key"。这对"用户各自的私有资源凭个人 token 访问"是硬缺口。本变更补齐 **per-user 动态 api-key/bearer**，作为 per-user OAuth 的简化同构姊妹能力。

## What Changes

- 新增 **per-user api-key/bearer 鉴权类型**（中立 `mcp_auth_models` 新 variant），区别于现有**静态 `api_key`（`key_env`）——静态行为不变**。token 按 `(user_id, agent_id, server_id)` 三元组隔离、per-request 注入（`Authorization: Bearer` 或 `X-API-Key`，按 server header 配置）。
- 无存储 token 时 `call_tool` 返回明确「需凭据」结果（不抛错、不卡住），触发用户提交流程。**两种提交方式，per-server 可配，默认模式 1**：
  - **模式 1（默认，安全表单）**：经现有 IM/directed-reach **DM** 一条一次性短 TTL、`state` 绑定 `(user,agent,server)` 的链接；链接指向 **fleetent 自托管表单**（standalone=agent 自托管 / managed=platform）；用户填 key 提交 → 服务端凭 `state` 反查三元组、**密文存储**。**零平台登录**（身份来自 DM 链接的一次性 `state`，沿用 OAuth 回调"MUST NOT 依赖登录态"模型）；token 不进对话历史。
  - **模式 2（opt-in 可配，对话内工具）**：agent 暴露 `set_mcp_credential` 工具，用户在对话（**限私信 DM**，防频道泄密）直接提供 token → 存 per-user。
- 与 OAuth 不同：**无 OAuth 提供商、无 PKCE/code 交换、无 refresh**；key 被吊销则用户重交。
- standalone 与 managed 两态经既有注入缝并存。

## Capabilities

### New Capabilities
- `mcp-per-user-apikey`: per-user 动态 api-key/bearer 凭据——新鉴权类型 + 无凭据触发 + 两种提交方式（默认安全表单 / 可配对话内工具）+ 三元组隔离存储 + per-request 注入；standalone（agent 自托管表单/本地库）与 managed（platform 表单端点 + node loopback + 管理库）两态;零平台登录。

### Modified Capabilities
- `mcp-auth-config`: discriminated union 新增 per-user api-key/bearer 鉴权类型 + per-server 提交方式配置项（form-only 默认 / tool / both）；静态 `api_key` 语义不变。

## Impact

- **复用 per-user OAuth 基础设施**：三元组 `mcp_user_tokens` 存储（api-key 放 access_token，refresh_token/expiry 为空）、注入缝 `set_user_token_resolver`（OAuth 与 api-key 共用 `resolve_user_token` 统一入口）、per-request 注入（`_PerUserBearerAuth` / stdio env）、无-token degrade 触发、DM 链接投递（`set_authorization_link_deliverer`）、managed 的 node loopback 通道 + platform 提交端点（与 oauth callback/pending 同构）。
- **新增**：中立 `mcp_auth_models` per-user api-key/bearer variant；凭据提交表单 + 提交端点（standalone agent `GET/POST /mcp/credential`；managed platform 端点 + node loopback 转发）；`set_mcp_credential` 内置工具（DM-gated）；per-server 提交方式配置。
- **契约守护**：agent runtime 仍 MUST NOT import platform；agent→platform 只经 node；明文 key 密文落库、不出对话、managed 下不出 platform（与 OAuth token 同等保护）。
- **Non-Goals**：撤销（revocation，后续切片）、静态 `api_key` 行为变更、OAuth 路径变更、MCP server 端实现。
