## Context

地基 harness（`e2e-managed-stack-coverage`）已落地：`tests/e2e/conftest.py::managed_stack` 起单 tenant 单 agent 的真实多进程栈，`tests/e2e/_llm_stub.py` 提供进程内 ASGI LLM stub（platform 进程经 env 指向它）。本 change 在其上加身份流覆盖，复用同一"env 指向进程内 stub"的注入范式。

已核实的真实路径（HEAD=90677480）：
- **OIDC 登录**：`GET /admin/oidc/login`（`platform/user_management/user_admin_api.py:117`，生成 state/nonce，set httponly cookie `fleetent_oidc_flow`，`build_authorize_url` 302 到 issuer）→ `GET /admin/oidc/callback`（:134，验 cookie flow→`exchange_code`(验 state/nonce/签名)→断言 `email_verified is True`→`resolve_or_provision`→建 session→302 `/admin/ui/login?token=`）。`OidcRelyingParty`（`oidc.py`），`OidcSettings`（`oidc_config.py`）。
- **配置加载**：`_oidc_settings()` 返回 `Settings().oidc`；`Settings` 是 `BaseSettings`，`model_config = SettingsConfigDict(env_nested_delimiter="__")`，`oidc: OidcSettings` 为嵌套字段 → `OIDC__ENABLED` / `OIDC__ISSUER` / `OIDC__CLIENT_ID` / `OIDC__REDIRECT_URI` / `OIDC__TENANT` 可注入，client secret 经 `client_secret_env` 指定的 env 名注入。（已核实嵌套分隔符为 `__`；apply task 1 探针仍须实跑确认 platform 子进程真读到。）
- **email 并号**：`resolve_or_provision`（`im_gateway_management/identity.py`）+ `get_by_email`（`user_store.py`，tenant 作用域 + 小写标准化）。唯一约束 migration 100：`uq_users_tenant_email_not_null ON users(tenant_id, email) WHERE email IS NOT NULL`。directed-reach 未改 `resolve_or_provision`。
- **/link**：`POST /admin/link/initiate`（`user_admin_api.py:248`，session auth via `_current_user`→生成 code，`_pending_links.put` TTL 600s）→ `POST /nodes/{node_id}/link-confirm`（`node_management/node_desired_state_api.py:160`，`_authenticate_node` node-key auth，`pop_valid`→冲突查 `get_mapped_user`→`attach_identity`，返回 `{user_id, tenant_id}`）。`POST /admin/link/unlink`（session auth）。directed-reach 在 `node_desired_state_api.py` 只新增 `/identity/resolve`、`/identity/addresses`，**未动 link-confirm**。

mock issuer 要实现：`/.well-known/openid-configuration`、`/oauth/authorize`（302 带 code + 透传 state）、`/oauth/token`（返 RS256 签名 id_token，claims: iss/aud/sub/nonce/email/email_verified）、jwks（RS256 公钥）。`joserfc` 已是项目依赖。

## Goals / Non-Goals

**Goals**：端到端经真实 HTTP 边界证明三条身份路径——OIDC 登录建 User、email 并号收敛同一 user_id、跨渠道 link 绑定/解绑；mock OIDC issuer 仿 `_llm_stub.py`，注入全在已有 HTTP/env 边界，零 src 改动、不改 `managed_stack` 核心。

**Non-Goals**：不测真实外部 IdP（仅 mock issuer）；不测真实 IM transport（`/link` 走 `link-confirm` HTTP 端点模拟 node edge）；不测 OIDC adapter 的 web-chat/open-API 范围（仍 deferred）；不重构核心 `managed_stack` / `conftest.py` 核心。

## ⚠️ 关键可行性风险（apply 第一步 task 组 1 探针必须先验，不得假设）

1. **mock OIDC issuer 起法 + 签名验过**：仿 `reserve_port`（`_llm_stub`）起进程内 ASGI；platform 的 `OidcRelyingParty.exchange_code` 要能用 mock 的 jwks（RS256 公钥）验过 id_token 签名，并验 `nonce`。**nonce 透传链是关键**：login 生成 nonce 写进 `fleetent_oidc_flow` cookie，callback 从 cookie 恢复 expected_nonce；mock authorize 必须把 nonce 透传到 id_token claim（authorize 收到的 nonce 参数原样回填 token），否则 nonce mismatch 验不过。探针先单独验"mock 签的 id_token 能被 OidcRelyingParty 验过"。
2. **OIDC 配置经 env 注入 platform 子进程的真实 key 名 / 嵌套分隔符**：已核实 `env_nested_delimiter="__"` + 嵌套 `oidc` 字段 → `OIDC__*`；但 platform 子进程是经 `managed_stack` 起的独立进程，须探针确认这些 env 真传到子进程且 `Settings().oidc.enabled` 为 True（区分进程内读 env vs `platform.yaml` 加载顺序）。
3. **cookie / CSRF 跨 login→callback**：用同一 `httpx.Client`（带 cookie jar）保证 `fleetent_oidc_flow` httponly cookie 在 login 响应被收下、callback 请求带回；TTL 300s（`flow_cookie_ttl_seconds`）内跑完整个 e2e 流程。
4. **/link 纯 HTTP 边界可行性**：initiate 需 session auth（已登录 User 的 session token）拿 code；link-confirm 需 node-key auth → 探针确认 node-key 从哪来（`managed_stack` 起 node 时的 node 注册凭证 / desired-state API 的 `_authenticate_node` 期望的头）。确认无需真 IM transport 即可走通 initiate→confirm。
5. **状态隔离**：每个 e2e 用 function-scoped `managed_stack`（platform 进程独立）→ `PendingLinkStore`（进程内 TTL store）、OIDC flow cookie/state 天然按进程隔离，确认 fixture scope 为 function（不复用进程），避免跨用例串状态。

## Decisions

- **mock OIDC issuer 作为进程内 ASGI stub（`_oidc_stub.py`），仿 `_llm_stub.py`**：`reserve_port` + 起 uvicorn/ASGI；platform 进程经 `OIDC__ISSUER` env 指向它。最小实现发现/authorize/token/jwks 四端点 + RS256 自签密钥对（`joserfc`）。
- **OIDC 配置经 env 注入，不写 platform.yaml**：`OIDC__ENABLED=true` 等 env 传给 platform 子进程（探针确认子进程读到）；secret 经 `client_secret_env` 指定的 env 名。复用既有 `Settings.oidc` namespace，零 src 改动。
- **/link 走 HTTP 边界，不起真 IM transport**：initiate（session token）→ link-confirm（node-key）→ 断言 `get_mapped_user`/unlink。这也是本 change 与 Wave B（改 IM transport）零文件重叠、可并行的根据。
- **helper 独占文件**：`_oidc_stub.py` + `_identity_helpers.py` 为本 change 独占；不碰 `conftest.py` 核心、不改 `managed_stack`、不改任何 src → 与并行波零合并冲突。
- **独立于 Wave B**：B 改 IM 入站审批 / transport；本 change OIDC 与 IM transport 无关，`/link` 经 HTTP 端点 → 两波互不依赖、可并行落地。

## Risks / Trade-offs

- mock issuer 签名验不过（nonce/jwks/aud mismatch）→ task 组 1 探针先单独把"mock 签 → RP 验过"打通再写流程用例。
- env 注入 platform 子进程不生效（被 platform.yaml 覆盖 / 子进程未继承）→ 探针定位，必要时调整 fixture 传 env 的方式（仍不改 src）。
- OIDC 流 TTL 300s → 用例须在单个 client 会话内紧凑跑完，不引入慢操作。
- 起 OIDC stub + 多进程栈增加启动时间 → e2e 在 slow lane，可接受。
