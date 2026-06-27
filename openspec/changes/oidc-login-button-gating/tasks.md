## 1. 配置字段

- [ ] 1.1 `OidcSettings`(`src/fleetent/oidc_config.py`)新增 `button_label: str = ""`;确认 `config.py` 配置源优先级链对其生效

## 2. 免鉴权配置端点（TDD）

- [ ] 2.1 写测试（红）：integration 测 `GET /admin/oidc/config`——未启用 → `200 {enabled:false, label:""}`;启用 + `button_label="Sign in with Google"` → `200 {enabled:true, label:"Sign in with Google"}`;**安全断言**:响应键集合恰为 `{enabled, label}`,响应体不含 client_secret / issuer / client_id 子串;端点**无需鉴权**即可访问
- [ ] 2.2 实现（绿）：在 `user_admin_api.py` 的 oidc 路由旁加 `GET /admin/oidc/config`,直接读 `Settings().oidc`,用显式 response model/dict 白名单构造 `{enabled, label}`(不序列化整个 OidcSettings);未启用照常返回 200 + `enabled:false`(不复用 `_require_oidc_settings`)。跑 2.1 见绿

## 3. 前端登录页条件渲染（TDD）

- [ ] 3.1 写测试（红）：登录页组件测——config `enabled:false`(及加载中/请求失败)时**不渲染** SSO 按钮;`enabled:true` + label 非空 → 渲染且文案=label;`enabled:true` + label 空 → 文案回落 `t('login.signInWithSso')`
- [ ] 3.2 实现（绿）：加 `useOidcConfigQuery`(免 auth,fetch `/admin/oidc/config`),登录页 `enabled===true` 才渲染 SSO 按钮,文案 `config.label || t('login.signInWithSso')`;加载/失败 fail-safe 不渲染。跑 3.1 见绿

## 4. 配置示例

- [ ] 4.1 更新 `platform.yaml.example` 的 `oidc` 段:加 `button_label` 示例 + 注释(空=用默认 "Sign in with SSO";可设成 "Sign in with Google" 等)

## 5. change 收尾

- [ ] 5.1 后端受影响层：`uv run pytest tests/integration/test_oidc_user_admin_api.py -q`(及相关）无新增失败
- [ ] 5.2 前端：`make test-frontend`(vitest+tsc+eslint)全绿
- [ ] 5.3 `make test-pr` + `make test-integration-ci` + `make test-unit-ci`(coverage ≥ 阈值)对照 main 基线无新增失败;`make frontend-build` 产物正常
- [ ] 5.4 本 change 触及文件：`uv run ruff format` / `ruff check` / `mypy src` 全绿
