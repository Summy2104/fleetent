> ⚠️ apply 排在 G(build-and-serve-frontend-on-deploy)落地之后(server.py 相邻行重叠)。TDD 硬门禁:先写测试见红 → 实现见绿。合并由窗口自合(当前约定)。

## 0. 退役前复核

- [ ] 0.1 `git grep -n "admin/ui-legacy"` 与 `git grep -n "admin.html"` 确认前端/文档无残留引用(已核实,apply 时复核一次防期间新增);如有引用先处理。

## 1. 移除 legacy 托管(server.py,TDD)

- [ ] 1.1 写测试(integration):`GET /admin/ui-legacy` 返回 **404**(不再托管);`/admin/ui` SPA 与 `/admin/*` API 不受影响。先见红(当前 legacy 返回 200)。
- [ ] 1.2 实现:`server.py` 删 `LEGACY_ADMIN_UI_PATH`、`_legacy_admin_html`、`@app.get("/admin/ui-legacy")` 路由。跑 1.1 见绿。

## 2. 删文件 + 清前端残留

- [ ] 2.1 删除 `src/fleetent/static/admin.html`。
- [ ] 2.2 清理 `frontend/src/app/routes.tsx` 残留的 `legacyLinks` 脚手架(已空)与 `routes.test.tsx` 相关断言;`make test-frontend` 仍绿。

## 3. Change 收尾验证

- [ ] 3.1 `make test-pr` + `make test-unit-ci` 全绿(对照 main 基线无新增失败);1.1 的 404 集成测试通过。
- [ ] 3.2 `make test-frontend` 绿。
- [ ] 3.3 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` 通过。
- [ ] 3.4 手动:`/admin/ui` 全功能在;`/admin/ui-legacy` 404;无残留 legacy 引用。
