## 1. 探针：先验四条可行性风险（先于任何流程用例）

- [ ] 1.1 **探针 · mock issuer 签名验过**：起最小 `_oidc_stub.py`（`reserve_port` + ASGI，RS256 自签密钥对，jwks/token 端点），构造一个带 `iss`/`aud`/`sub`/`nonce`/`email`/`email_verified` 的 id_token，用 platform 的 `OidcRelyingParty`（指向 stub 的 jwks）验签 + 验 nonce 走通。记录：nonce 透传链（authorize 收到的 nonce → token claim）、aud/iss 须匹配 client_id/issuer。**不假设**。
- [ ] 1.2 **探针 · OIDC env 注入 platform 子进程**：经 `managed_stack` 的起栈方式给 platform 子进程注入 `OIDC__ENABLED=true` / `OIDC__ISSUER=<stub>` / `OIDC__CLIENT_ID` / `OIDC__REDIRECT_URI` / `OIDC__TENANT` + secret env，断言 `GET /admin/oidc/login` 返回 302 到 stub authorize（证明 `Settings().oidc.enabled` 在子进程为 True）。记录真实 env key 名 / 是否被 platform.yaml 覆盖。
- [ ] 1.3 **探针 · cookie 透传**：用同一 `httpx.Client`（cookie jar）请求 login → 确认收到 httponly `fleetent_oidc_flow` cookie → callback 请求带回。记录 TTL 与 client 复用姿势。
- [ ] 1.4 **探针 · link-confirm node-key 来源**：定位 `managed_stack` 起 node 时的 node-key / `_authenticate_node` 期望的认证头，确认 initiate（session token）→ link-confirm（node-key）可纯 HTTP 走通，无需真 IM transport。记录 node-key 取得方式。

## 2. mock OIDC issuer harness（`_oidc_stub.py`）

- [ ] 2.1 **测试（红）**：在本 change 的 e2e test 文件写一个用例——起 `_oidc_stub.py` ASGI app，断言 `/.well-known/openid-configuration`、`/oauth/authorize`(302+code+透传 state)、`/oauth/token`(RS256 id_token)、jwks 四端点行为正确，且 `OidcRelyingParty` 能验过其签发的 id_token。先跑最窄命令见红（`uv run pytest tests/e2e/<file>::<test> -x -q`）。
- [ ] 2.2 **实现（绿）**：实现 `tests/e2e/_oidc_stub.py`（仿 `_llm_stub.py` 结构）+ `_identity_helpers.py` 中起 stub / 配 env 的 helper。跑同一命令见绿。

## 3. E2E-1 OIDC web 登录建 User

- [ ] 3.1 **测试（红）**：用 `managed_stack` + `_oidc_stub`（platform env 指向 stub），同一 `httpx.Client` 走 `GET /admin/oidc/login` → 带 stub 的 code/state 走 `GET /admin/oidc/callback`，断言：建出 User（email == id_token claim、tenant == 配置 tenant）、回调 302 到带 session token 的 `/admin/ui/login?token=`。先跑见红。
- [ ] 3.2 **绿**：让它过（若红，定位 OIDC 流哪段——这正是 e2e 要抓的回归）。

## 4. E2E-2 email 并号收敛同一 user_id

- [ ] 4.1 **测试（红）**：同一 tenant 下先建一个 email 为 `X` 的 User（经先行路径：IM 担保身份或直接建号），再以 id_token claim `email=X` 走 OIDC `/admin/oidc/callback`，断言：返回的 user_id 等于先前 User 的 user_id、users 表该 tenant+email 仍只一条（不重复建号，命中唯一约束语义）。先跑见红。
- [ ] 4.2 **绿**：让它过。

## 5. E2E-3 跨渠道 /link initiate→confirm→bind（+unlink）

- [ ] 5.1 **测试（红）**：以已登录 User 的 session token `POST /admin/link/initiate` 拿 code → 以 node-key `POST /nodes/{id}/link-confirm` 带 `{platform, platform_user_id, code}` → 断言绑定到该 user_id、响应含 user_id/tenant_id、`get_mapped_user` 映射一致；再断言重复 code → 404、冲突身份 → 409；最后 `POST /admin/link/unlink` 解绑 → `get_mapped_user` 返空。先跑见红。
- [ ] 5.2 **绿**：让它过。

## 6. 收尾 + lane + 边界自检

- [ ] 6.1 `make test-e2e` 跑这批（含 `_oidc_stub.py` + `_identity_helpers.py` + 3 个流程用例 + harness 用例）；确认**不在** `make test-pr` 里。
- [ ] 6.2 `make test-pr` 仍全绿（本 change 纯 test 侧、不碰 src，对照 main 基线无新增失败）。
- [ ] 6.3 边界自检：仅新增 `tests/e2e/_oidc_stub.py` + `tests/e2e/_identity_helpers.py` + 本 change 的 e2e test 文件；**未改** `tests/e2e/conftest.py::managed_stack` / conftest 核心、未改任何 src。如确需改核心 fixture 或 src，停下说明（违反并行纪律 / 触碰契约）。
