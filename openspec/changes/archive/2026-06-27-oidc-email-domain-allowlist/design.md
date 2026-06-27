## Context

OIDC web 登录已落地(`admin-auth` 能力)。回调 `src/fleetent/platform/user_management/user_admin_api.py:135` 当前流程:解码 flow cookie → `OidcRelyingParty.exchange_code`(校验 state/nonce/签名/issuer/audience/exp)→ 校验 `email_verified===true` 且 email 非空 → `_oidc_tenant_for(email, claims, settings)`(当前 stub,返回单 tenant)→ `resolve_or_provision(tenant, verified_email=...)` 找到或建 email-keyed user → 签 session。配置在 `src/fleetent/oidc_config.py` 的 `OidcSettings`。

缺口:`email_verified` 是 IdP 侧"这个邮箱属实"的断言,不等于"这个邮箱该被允许进本平台"。后者是平台的授权决策,当前完全缺失。

## Goals / Non-Goals

**Goals:**
- 平台层可配置的邮箱域白名单,把"谁能经 OIDC 进来"从纯依赖 IdP 设置收回到平台配置。
- 默认空 = 零行为变化,向后兼容;OIDC 仍默认 disabled。
- provider 无关,不破坏现有"不硬编码 provider"铁律。

**Non-Goals:**
- per-tenant IdP / 邮箱域→tenant 映射(deferred 的 variant B/C,不碰 `_oidc_tenant_for`)。
- claims/groups→角色映射(另一项 deferred)。
- 任何前端改动、任何 DB/schema/迁移。
- 正则/通配符匹配(本次只做精确域匹配,保持可预测)。

## Decisions

**D1 — 域校验抽成纯函数,放在 `oidc.py`。** 新增形如 `email_domain_allowed(email: str, allowed_domains: list[str]) -> bool` 的纯函数(空 domains → True;否则取 `email.rsplit("@",1)[-1].lower()` 精确比对 `{d.lower() for d in allowed_domains}`)。理由:纯函数易 unit 测全分支(大小写/子域/空/多域/畸形 email),回调只做"调用 + 拒登"。备选(内联进回调)被否:逻辑混进 HTTP handler 难单测。

**D2 — 闸口位置:`email_verified` 之后、`resolve_or_provision` 之前。** 域门控是授权前置,必须早于任何建号/并号副作用。放在已有 email_verified 校验紧后一行,自然衔接。对已有 user 同样拦截(域门控不查库、不区分新老),符合 spec"一视同仁"。

**D3 — 匹配 email 域,不读 `hd` claim。** 遵守 D1(归档 spec)"不写 per-provider 分支"。`hd` 是 Google 专有,用它就破坏 provider-agnostic。email 域对所有 OIDC provider 通用。代价:Google 的 `hd`(hosted domain)与 email 域在极少数别名场景可能不同,但 email 域是更通用且用户直觉一致的判据。

**D4 — 精确域匹配,子域不自动包含。** `acme.com` 不覆盖 `eu.acme.com`。理由:最小惊讶 + 最严格默认,要放宽就显式列子域。备选(后缀匹配 `.acme.com`)被否:易误放行 `evil-acme.com` 之类,且引入歧义。

**D5 — 拒登用 403(非 401)。** 与回调中既有"账号非 active"用 403 一致;401 在本回调语义里是"认证流程本身失败(state/nonce/token 校验)",而域不允许是"认证成功但不授权",403 更准确。detail 明确"email domain not allowed"。

## Risks / Trade-offs

- **[管理员配置白名单后,已有域外 user 被挡在 OIDC 外] → Mitigation**:这是预期的安全行为(spec 明确"一视同仁");此类 user 若仍需访问,可走 email/password 路径(若有)或由管理员调整白名单。在 `platform.yaml.example` 注释里点明该语义。
- **[email 域大小写 / 前后空白 / 多 @ 畸形输入] → Mitigation**:纯函数统一 `.lower()` 且用 `rsplit("@",1)` 取最后一段;畸形(无 @)→ 取不到合法域 → 不匹配 → 拒登(fail-closed,安全侧)。unit 测覆盖这些边界。
- **[与 `hd` 的语义差异让用 Google Workspace 的管理员困惑] → Mitigation**:文档说明本白名单基于 email 域;Google 侧仍可叠加 OAuth 应用的 Internal/域限制,两者不冲突、可并用。

## Migration Plan

1. 加 `OidcSettings.allowed_email_domains: list[str] = []`(默认空,向后兼容)。
2. 加纯函数 + 回调接线 + integration 测 + `platform.yaml.example` 更新。
3. 回滚:纯 `git revert`;无 DB/状态。旧配置无该字段 → pydantic 默认空 → 不限制,平滑。

## Open Questions

- 域校验被拒登时是否要写 `platform-audit-log` 审计条目?该能力要求"所有 admin 写操作可审计",但拒登并非写操作、也无既定 actor(身份尚未确立)。本次倾向**仅结构化日志记录(structured_logging)拒登事件**,不强行塞进 audit 表;若后续有合规需求再单议。实现时按此处理,落到 tasks。
