## Context

`server.py`:`LEGACY_ADMIN_UI_PATH = .../static/admin.html`(66)、`_legacy_admin_html()`(255)、`@app.get("/admin/ui-legacy")`(277)。`static/admin.html` 4731 行单文件。已核实 origin/main 前端无 `/admin/ui-legacy` 深链、`routes.tsx` 的 legacyLinks 已空。所有域 + agent 绑定均原生。

## Goals / Non-Goals

**Goals:** 干净退役 legacy(删文件 + 托管 + spec 共存要求);`/admin/ui` 成为唯一管理台。
**Non-Goals:** 不动任何原生域;不碰 agent/schema;不在 G 落地前 apply(server.py 重叠)。

## Decisions

**D1 · 删除三处 + 文件。** server.py 移除 `LEGACY_ADMIN_UI_PATH`/`_legacy_admin_html`/`/admin/ui-legacy` 路由;删 `static/admin.html`;清 `routes.tsx`/`routes.test.tsx` 的 legacyLinks 残留(已空,确保彻底)。`/admin/ui-legacy` 返回 404(FastAPI 默认),并加测试断言它确实 404(防 fallback 误吞)。

**D2 · 排在 G 之后 apply。** D2 与 G 都改 server.py 顶部相邻行(ADMIN_UI_DIST_DIR vs LEGACY_ADMIN_UI_PATH)。**apply 必须等 G 合入 main**,从 post-G main 起分支,避免相邻行冲突。propose(产 artifacts)现在做、零冲突。

**D3 · 退役前再 grep 兜底。** apply 时先 `git grep -n "admin/ui-legacy"` 确认前端/文档无残留引用再删(已核实但 apply 时复核一次,防期间新增)。

**D4 · 可逆。** 删 admin.html 经 git 历史可恢复;spec 共存要求移除后若需回退可 revert 本 change。

## Risks / Trade-offs

- **[误删仍被依赖的 legacy]** → 已核实零深链 + 所有域原生;apply 时再 grep 复核;可 git 恢复。
- **[与 G 撞 server.py]** → D2 apply 排 G 之后;若仍小冲突(相邻行),解完 grep 冲突标记为空。
- **[漏掉某域的 parity]** → 各迁移 change 已逐域对 parity;retire 只移除入口,不改任何原生域功能。
