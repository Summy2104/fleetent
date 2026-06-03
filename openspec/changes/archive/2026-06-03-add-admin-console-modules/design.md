## Context

`admin.html` 是自包含 vanilla-JS SPA：顶部 tabs → `switchTab()` 切 section → 每 tab `load*()` 调 `api(method, path, body)`（自动加 `/admin` 前缀，带 Session header）→ 渲染表格 + modal。既有 tab：Users / IM Users / Connectors / KB / Audit。角色门禁在 `enterApp()`：viewer 隐藏写控件。

后端 13 个路由已全部 `include_router`，覆盖 8 个待补管理域（见 proposal）。本变更主要是**前端接线**：复用既有 JSON API，不重写后端。

挑战：tab 从 5 增到 13，单栏 tab bar 会挤；且 `admin.html` 单文件会显著变大。

## Goals / Non-Goals

**Goals:**
- 8 个域各自完整管理面（覆盖该域 admin 端点）。
- 保持单文件 vanilla JS、无框架、无构建、无新依赖。
- 写操作 admin-only + viewer 隐藏；secret 掩码读、不预填密文。
- 每域 UI 断言测试 + 浏览器逐 tab 验证。

**Non-Goals:**
- 不重写/不美化既有 5 个 tab（除导航改造必需）。
- 不实现实时流（SSE）的完整 UI；stream 端点先用「触发 + 轮询/一次性读」占位，完整流式留后续。
- 默认不加后端端点；仅在动作缺端点时增补（届时该 task 注明 + 后端测试）。

## Decisions

**D1: 二级导航分组，避免 tab 挤爆。**
顶部一级分组：`Access`（Users / IM Users）、`Agents & Skills`（Agents / Skills）、`Models & Connectors`（Providers / OAuth+MCP / IM Connectors）、`Ops`（Stats / Monitoring / Sessions / AskIt）、`Audit`。一级选组 → 二级 tab 行渲染该组的 tab。`switchTab` 扩成 `switchGroup`+`switchTab`。备选：扁平 13 tab（简单但拥挤）。**决定**：二级分组，更可用且 admin.html 结构清晰。

**D2: 每域一个 section + 一组 `load<Domain>()` / 动作函数，命名空间前缀避免冲突。**
函数名前缀：skill→`sk*`、provider→`pv*`、agent→`ag*`、stats→`st*`、monitoring→`mon*`、session→`sess*`、oauth/mcp→`oc*`/`mcp*`、askit→`ak*`。元素 id 同前缀（`sk-body`、`pv-modal`…）。

**D3: 复用既有 modal/表格 CSS + `api()`/`esc()`/menu 模式。**
新代码沿用 `.modal`/`.menu`/`.pill`/`.actions`，零新 CSS（必要时极少补）。写操作走既有 dropdown menu 或行内按钮。

**D4: secret 字段。**
provider / oauth connector 的凭证读取走后端已有掩码视图；新增/编辑表单 `type=password autocomplete=off`，编辑不预填密文，留空表示不改。

**D5: stream 端点降级处理。**
`/chat/{id}/stream`、`/askit/tasks/{id}/stream` 本期不接 SSE；用非流式 `message` / `tasks/{id}` 轮询读结果，UI 注明。完整流式单列后续。

**D6: 测试策略。**
每域 UI 断言测试读 `admin.html` 文本，断言该域 tab 标记、关键控件 id、动作函数名与端点路径出现（模式同 im-connector-admin-ui 已落地测试）。后端若增补端点，按 TDD 加 FastAPI TestClient 测试。浏览器逐 tab functional 验证（stub `window.api` 抓 payload + DOM 断言）。

## Risks / Trade-offs

- [admin.html 过大难维护] → 本期接受单文件（项目约定）；若超出可读阈值，后续单列「拆分静态资源」变更，不在本次。
- [前后端端点漂移] → UI 测试断言端点路径字符串出现；端点改名会触发测试失败。
- [stream 降级体验不完整] → 明确标注 Non-Goal，先保证可见性与基本操作。
- [范围大、一个 change 跨多模块] → tasks.md 按域分组，apply 阶段逐域红绿落地、逐域可独立验证；任一域可单独 review。
- [写操作风险（force-end/clear/revoke 等破坏性）] → 前端二次确认（confirm），且 admin-only；不在前端绕过后端校验。

## Migration Plan

1. 改造导航为二级分组（含既有 5 tab 归组），保证现有功能不回归。
2. 逐域加 section + JS 接线 + 测试（TDD），顺序：Skills → Providers → Agents → Stats → Monitoring → Sessions → OAuth+MCP → AskIt。
3. 收尾跑 ruff/mypy/全量 pytest + 浏览器逐 tab 验证。
无 DB migration（除非端点增补需要）。回滚 = 还原 admin.html（及任何增补端点）。

## Open Questions

- 是否需要 SSE 流式 UI（chat/askit）——本期降级，待用户确认是否单列后续变更。
