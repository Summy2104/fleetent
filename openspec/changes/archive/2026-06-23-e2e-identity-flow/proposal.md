## Why

身份模型是 fleetent 的核心契约：一切主体都是 `User`，认证发生在 edge，跨渠道经 `/link` 并成一人，OIDC web 登录与 IM 担保身份经同一 `resolve_or_provision` 收敛到 email 唯一约束。这三条路径（OIDC 登录建 User、email 并号、跨渠道 link）至今**只有单进程 unit/integration 覆盖**——没有一条 e2e 在真实多进程 managed 栈下证明"web OIDC 登录建出 User"、"先 IM 后 OIDC 同 email 收敛同一 user_id 不重复"、"`/link` 把两个渠道身份绑到同一人"。身份串号/重复建号是 P1 安全回归，回归代价极高，必须有端到端守门。地基 harness（`e2e-managed-stack-coverage` 的 `managed_stack` + `_llm_stub`）已落地，正好解锁这条覆盖。

## What Changes

- 新增 e2e：在多进程 managed 栈下，经**真实 HTTP 边界**覆盖三条身份路径，零 src 改动：
  - **OIDC web 登录建 User**：platform 进程经 env 指向本地 **mock OIDC issuer**（新建 `tests/e2e/_oidc_stub.py`，仿 `_llm_stub.py`），走 `GET /admin/oidc/login` → `GET /admin/oidc/callback` 完整流程，断言建出 User（email / tenant / session token 正确）。
  - **email 并号**：先经 IM 担保身份（或先建 User）落一个 email，再以**同 email** 走 OIDC 登录，断言 `resolve_or_provision` 收敛到**同一 user_id**、不重复建号（命中 migration 100 的 `uq_users_tenant_email_not_null` 唯一约束语义）。
  - **跨渠道 `/link`**：`POST /admin/link/initiate`（session auth 拿 code）→ 模拟 node edge `POST /nodes/{id}/link-confirm`（node-key auth，body `{platform, platform_user_id, code}`）→ 断言 im_users 绑定到该 user_id；再走 `POST /admin/link/unlink` 断言解绑。
- 新增 e2e 专属 helper：`tests/e2e/_oidc_stub.py`（mock OIDC issuer ASGI app，签 RS256 id_token + jwks）、`tests/e2e/_identity_helpers.py`（身份流编排 helper，本 change 独占）。
- **不重构核心 `managed_stack` fixture / `conftest.py` 核心**——OIDC 经 platform 进程读 env 指向 stub，`/link` 经现成 HTTP 端点，注入策略全在已有 HTTP 边界。
- 进 slow/nightly lane（`make test-e2e`），**不**进 per-merge `make test-pr`。

## Capabilities

### New Capabilities
- `e2e-identity-flow`: 多进程 managed 栈下的身份流端到端覆盖——mock OIDC issuer harness、OIDC web 登录建 User、email 并号收敛同一 user_id、跨渠道 `/link` initiate→confirm→bind（+unlink）。

### Modified Capabilities
（无；不改任何现有 capability 的 requirement，纯新增 e2e 覆盖。）

## Impact

纯测试侧改动，零 src 产品代码改动。

- **owning package**：`tests/e2e`（新增 test 文件 + `_oidc_stub.py` + `_identity_helpers.py`）；复用 `tests/e2e/conftest.py::managed_stack`、`tests/e2e/_llm_stub.py` 既有基建
- **public API surface**：无（纯测试侧；不新增/改 src public API）
- **owned tables**：无（只读验证现有 users / im_users 表的身份收敛与绑定行为；不新增/改 schema）
- **config namespace**：无（OIDC 配置经现有 `OIDC__*` env 注入 platform 进程，复用 `Settings.oidc` 既有 namespace，不新增）
- **cross-module dependencies**：测试经现成 HTTP 边界（`/admin/oidc/*`、`/admin/link/*`、`/nodes/{id}/link-confirm`）驱动既有 platform/node/agent 三进程；不引入 src 跨模块依赖
- **migration / shim**：无
- **受影响代码**：仅 `tests/e2e/`；核心 `managed_stack` fixture 与 `conftest.py` 核心 **冻结不动**（新增独占 helper 文件，避免与并行波撞 `conftest.py`）
- **与 Wave B 独立**：B（IM 入站审批）改 IM transport 侧；本 change 的 `/link` 走 `link-confirm` HTTP 端点（不需真 IM transport），OIDC 与 IM transport 无关 → 两波零文件重叠，可并行
- **CI**：进 `make test-e2e` slow/nightly lane，不进 per-merge 门禁
