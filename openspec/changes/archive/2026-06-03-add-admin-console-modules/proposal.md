## Why

后端已有 13 个 admin 路由覆盖全部平台管理域，但 admin 控制台（`admin.html`）只暴露 5 个 tab（Users / IM Users / Connectors / Knowledge Base / Audit）。Skills、Model Providers、Agents、Statistics、Monitoring+Alerts、Sessions、OAuth+MCP、AskIt 八个管理域**无任何 UI**，管理员只能走 CLI 或裸 HTTP。本变更把这八个域补全到控制台，做到完整管理面，复用既有 JSON API，不重写后端。

## What Changes

为以下八个域各加一个控制台 tab（必要时二级导航），覆盖该域全部 admin 端点；写操作 admin-only、viewer 隐藏；secret 读取走既有掩码：

- **Skills** `/admin/skills`：列表/创建/编辑/enable/disable/reload/delete/restore、agent 绑定、force-publish、observability、provenance promote/discard、proposal 审核（diff/approve/reject）。
- **Model Providers** `/admin/providers`：provider CRUD、connectivity-test、pricing、observability、task_type 路由（GET/PUT/preview）、health。
- **Agents** `/admin`（console+admin api）：templates、agent 列表/observability、enable/disable/archive/restore/clone、versions（列/activate）、user/channel 绑定。
- **Statistics** `/admin/stats`：agent overview/compare/tools、per-user、user requests、request 详情、session trace、export、reports。
- **Monitoring + Alerts** `/admin`：monitoring/metrics、alert rules CRUD、alerts 列表/ack/silence/maintenance。
- **Sessions** `/admin`（chat api）：sessions 列表/详情、takeover/release/inject/force-end/clear/reset、bulk、chat playground（start/message/stream/pin/export）。
- **OAuth Connectors + MCP** `/admin`（connector_management）：connector CRUD/lifecycle、grants 授权矩阵、offboarding、grant revoke、mcp doctor/servers/tools/reconnect。与既有 IM Connectors tab 区分（这是 OAuth/MCP，非 IM）。
- **AskIt** `/admin/askit`：series、run、tasks 列表/详情/stream。

前端保持单文件自包含 vanilla JS（tabs + 表格 + modal + `api()` helper），**不引入前端框架/构建步骤、无新依赖**。仅当某动作缺后端端点时才补端点（named SQL params、store 边界、Alembic 管 schema、无 ORM）。

## Capabilities

### New Capabilities
- `skill-admin-ui`: 技能管理控制台界面（列表/CRUD/启停/reload/绑定/发布/observability/provenance/proposal 审核）。
- `provider-admin-ui`: 模型供应商控制台界面（CRUD/连通性/定价/路由/health/observability）。
- `agent-admin-ui`: 智能体控制台界面（模板/列表/生命周期/版本/绑定/observability）。
- `stats-admin-ui`: 统计控制台界面（概览/对比/per-user/请求与 trace/导出/报表）。
- `monitoring-admin-ui`: 资源监控与告警控制台界面（指标/告警规则/告警处置/维护窗）。
- `session-admin-ui`: 会话管理控制台界面（列表/详情/接管/注入/结束/清理/playground）。
- `oauth-mcp-admin-ui`: OAuth 连接器与 MCP 控制台界面（连接器 CRUD/授权矩阵/offboarding/MCP 诊断）。
- `askit-admin-ui`: AskIt 控制台界面（series/run/tasks）。

### Modified Capabilities
- 无（默认纯前端接线复用既有端点）。若 apply 阶段发现端点缺失，再对相应既有 spec（如 `skill-admin-api`/`provider-admin-api` 等）补 delta，并在该 task 注明。

## Impact

- 代码：主要改 `src/fleetent/static/admin.html`（8 个 tab + modal + JS 接线）。后端仅在端点缺失时增补。
- API：默认无新端点；复用既有 `/admin/*`。
- 存储：无 schema 变更（除非补端点需要，届时走 Alembic）。
- 安全：写操作 admin-only、viewer 隐藏；secret 掩码读、不预填密文。
- 无新依赖；不引入前端框架；不触碰 agent loop。
- 测试：每域 UI 断言测试（读 `admin.html` 断言 tab/控件/动作 wiring）+ 浏览器逐 tab 验证；端点增补处加后端测试。
