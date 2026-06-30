## Context

`agent_config._reject_inline_secrets(agent, path)` 在加载 agent.yaml 时 `flatten` `mcp_servers`(+`im`) 的所有字符串值，对每个值 `looks_inline_secret(value) and not _is_env_reference(key, value)` 为真则抛错。`_SKIP_SECRET_SCAN_SEGMENTS` 列出结构性、非密字段（`.transport` / `.command` / `.id` / `.args.` / `.access.allow_*`）跳过扫描。`auth_type` 漏在其中：它是 pydantic 判别枚举，值形如 `oauth_authorization_code`，被 `looks_inline_secret` 误判为 True，又不以 `_env` 结尾。连接器物化出顶层 `auth_type` 后，agent boot 即崩。

## Goals / Non-Goals

**Goals:** 让 `auth_type` 判别枚举不被 inline-secret 守卫扫描，使连接器物化的 oauth_authorization_code / oauth_client_credentials agent 正常加载。

**Non-Goals:** 不改 `looks_inline_secret` 启发式；不放宽真正 secret 字段（`*_env` 仍豁免、token_url/authorization_endpoint/scope 等仍扫描）；不动 materialize / 连接器。

## Decisions

**D1：把 `.auth_type` 加进 `_SKIP_SECRET_SCAN_SEGMENTS`（与现有结构字段同列），而非改 `looks_inline_secret`。**
- 最小、最安全：只豁免一个已知结构性判别字段，不削弱对其它值的检测。
- `seg in key` 子串匹配：键 `mcp_servers.N.auth_type` 含 `.auth_type` → 跳过；不会误伤其它字段（无 secret 字段名含 `.auth_type`）。
- 备选（否决）：放宽 `looks_inline_secret` 对 `oauth_*` 串——影响面大、易回归。

## Risks / Trade-offs

- [跳过 auth_type 漏扫真实 secret] → auth_type 是枚举判别，取值受 pydantic Literal 约束，不可能承载 secret；豁免无安全损失。

## Migration Plan

纯代码、单元组豁免，无 schema/数据迁移。回滚=移除该项。

## Open Questions

无。
