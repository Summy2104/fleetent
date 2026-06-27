## 1. 配置字段

- [ ] 1.1 `OidcSettings`(`src/fleetent/oidc_config.py`)新增 `allowed_email_domains: list[str] = Field(default_factory=list)`;确认 `config.py` 配置源优先级链对该字段生效(init/env/yaml/secret)

## 2. 域匹配纯函数（TDD）

- [ ] 2.1 写测试（红）：`tests/unit/platform/user_management/` 下新增 `email_domain_allowed` 的 unit 测——空名单放行；域内大小写不敏感放行；域外拒；子域不被父域覆盖；多域名单；畸形 email（无 @）fail-closed 拒
- [ ] 2.2 实现（绿）：在 `src/fleetent/platform/user_management/oidc.py` 加纯函数 `email_domain_allowed(email, allowed_domains) -> bool`（空→True；否则 `rsplit("@",1)[-1].lower()` 精确比对小写集合），跑 2.1 见绿

## 3. 回调接线（TDD）

- [ ] 3.1 写测试（红）：integration 测 `/admin/oidc/callback`——配 `allowed_email_domains=["acme.com"]`，stub 出 verified email 为域外（gmail.com）→ 断言 403、不建号、不签 session；域内 → 断言照常签 session；已有 user 的域外邮箱 → 同样 403
- [ ] 3.2 实现（绿）：在 `oidc_callback`（`user_admin_api.py`）的 `email_verified`/email 非空校验之后、`resolve_or_provision` 之前插入域门控，不通过则 `raise HTTPException(403, "email domain not allowed")`；跑 3.1 见绿
- [ ] 3.3 在拒登分支加结构化日志（`structured_logging`）记录拒登事件（域、issuer），不写 audit 表（依 design Open Question 结论）

## 4. 配置示例与文档

- [ ] 4.1 更新 `platform.yaml.example` 的 `oidc` 段：加 `allowed_email_domains` 示例 + 注释（空=不限制、精确域匹配、子域需显式列、与 IdP 侧域限制可并用）

## 5. change 收尾

- [ ] 5.1 跑受影响层测试：`uv run pytest tests/unit/platform/user_management -q` 与对应 integration 测，确认无新增失败
- [ ] 5.2 跑 `make test-pr` + `make test-integration-ci`，对照 main 基线无新增失败
- [ ] 5.3 `uv run ruff format src tests` + `uv run ruff check` + `uv run mypy src`（本 change 触及的文件）全绿
