> **实施进度（opsx:apply，主体完成）**
> 已按 TDD 实现并通过（沙箱 3.10 + `.pth` UTC shim；不 import agent_loop）：
> - 决策落定：0.2 新建 `connectors` 配置表（迁移 `013`，`id`/`display_name`/`protocol`/`oauth_config` JSON/`enabled`），**client_secret 永不入表**（store add/edit 主动剥离）。0.4 脱敏在 API 层统一递归 `_mask`（覆盖 secret/token/refresh/api_key/password）。connectors / mcp / governance 运行语义走 mock 接缝（follow-up）。
> - 数据层：`connector_config_store.py`（db runtime + named params：add/edit/get/list，secret 剥离）。
> - 管理 API：`connector_admin_api.py`（`/admin/connectors/*` + `/admin/mcp/*`）——OAuth 目录 CRUD（仅 oauth2，非 oauth 422，secret 脱敏）、per-user 授权矩阵（四态 + token 脱敏）、**不可代 consent**（无代授权路由，矩阵返回提示）、代 revoke（二次确认 + admin）、离职联动结果、凭证生命周期、MCP server 列表（连接/降级/重连中/永久不可用）、`server__{tool}` 命名空间、手动重连、mcp doctor（脱敏）。
> - 接线：`server.py` mount。权限 `auth.has_role`（admin 写/viewer 只读）+ `audit_log` 审计。
> - 测试：新增 19 个（store 5 + api 14），覆盖场景 109–114；`ruff format/check` 通过。全量 + mypy + 冒烟需 host 3.12。

## 0. 前置

- [ ] 0.1 确认新模块边界：`connector_admin_api.py`（`/admin/connectors/*` + `/admin/mcp/*`，仿 `user_admin_api.py`，不 import `agent_loop`）；是否拆出 `connector_config_store.py` 承载 connector 配置 store
- [ ] 0.2 确认 connector 配置表归属：是否新建 `connectors` 配置表（`id` / `display_name` / `oauth_config` JSON / `enabled` / `created_at`），还是 connectors 域已建则本面只读复用；**client_secret 不入表**（走 env / 密钥注入）
- [ ] 0.3 确认是否需要 Alembic 迁移：若本 change 新建配置表则走 Alembic（不在 store `_init_db()` 建表）；named params（`:x`），路径可 monkeypatch
- [ ] 0.4 确认脱敏在序列化层统一处理：定义单一 `_mask` 序列化器覆盖 `client_secret` / access token / refresh token / MCP 认证值，所有 `/admin/*` 响应与审计 `detail` 经其处理
- [ ] 0.5 确认跨域只读接口与触发动作契约（follow-up）：connectors 暴露授权状态查询 + `revoke(user_id, connector_id)` + 离职联动结果查询；mcp 暴露连接状态查询 + 注册工具清单 + 手动重连 + `mcp doctor`；governance 消费 `server__*` 清单

## 1. connector 配置 store（按 0.x 决策）

- [ ] 1.1 Write failing tests: `connectors` 配置表含 `id`/`display_name`/`oauth_config`/`enabled`/`created_at`；`add_connector` / `edit_connector` / `list_connectors`；client_secret 不入表
- [ ] 1.2 实现 `connector_config_store.py`（named params，路径可 monkeypatch，schema 走 Alembic）
- [ ] 1.3 Write failing tests: 序列化层 `_mask` 对 client_secret / token 输出脱敏占位，绝不回明文
- [ ] 1.4 实现脱敏序列化器（统一被各端点复用）

## 2. connector 目录 + 配置 CRUD（脱敏）

- [ ] 2.1 Write failing tests（TestClient）: 无 session 401；viewer 可 GET 目录、写 403；admin 可新增 / 编辑 connector 配置；列表 client_secret 脱敏
- [ ] 2.2 实现 `connector_admin_api` 的 `/admin/connectors` 目录 GET + 配置 POST/PUT（复用 `auth.has_role` / `require_role`，写审计）
- [ ] 2.3 Write failing tests: 仅 OAuth 2.x，新增表单 / API 不接受非 OAuth 接入类型；保存即生效

## 3. per-user 授权矩阵 + 不可代 consent 守卫

- [ ] 3.1 Write failing tests: mock connectors 授权状态查询，矩阵渲染 未授权(NeedsConsent 未授过) / 已授权+scopes / 失效需重授(NeedsConsent refresh 过期) / 凭证错误(CredentialError)（场景 109）
- [ ] 3.2 实现 `/admin/connectors/grants` 矩阵端点（消费 connectors 只读查询，按 user / 按 connector 两视角聚合，状态不在本面重算）
- [ ] 3.3 Write failing tests: 未授权格无代授权入口；不存在代 consent 端点；明示需本人浏览器跳转（场景 110）
- [ ] 3.4 实现不可代 consent 守卫（无代授权路由，未授权格返回提示文案）

## 4. 代用户 revoke + 离职联动可视 + 生命周期观测

- [ ] 4.1 Write failing tests: admin revoke `(user, connector)` 二次确认 → 调 connectors `revoke` → 写审计；viewer revoke 403（场景 111）
- [ ] 4.2 实现 `/admin/connectors/grants/{...}/revoke`（委托 connectors，二次确认，批量关联批次 ID，写审计）
- [ ] 4.3 Write failing tests: 禁用用户后展示 connectors 自动撤销结果（哪些 connector、成功 / 失败）
- [ ] 4.4 实现离职联动结果视图（消费 connectors 离职联动查询）
- [ ] 4.5 Write failing tests: 按 connector 展示 refresh 成功 / 失败率 + 重新授权次数
- [ ] 4.6 实现凭证生命周期观测视图

## 5. MCP server 列表 + 连接状态 + 命名空间

- [ ] 5.1 Write failing tests: mock mcp 连接状态查询，列表渲染 已连接 / 启动时降级屏蔽(工具数 0) / 探活失败重连中 / 标记永久不可用；降级 server 提供手动重连入口（场景 112）
- [ ] 5.2 实现 `/admin/mcp/servers` 列表端点（消费 mcp 只读状态查询，状态不在本面重算）
- [ ] 5.3 Write failing tests: 展开 server 列出 `server__{tool}` 命名空间 + 名称 / 描述 / 入参 schema 概要（场景 113）
- [ ] 5.4 实现 `/admin/mcp/servers/{id}/tools` 工具清单端点（双下划线命名空间，供 governance allowed_tools 参考）

## 6. 手动重连 + mcp doctor（脱敏）+ 权限审计

- [ ] 6.1 Write failing tests: admin 手动重连触发 mcp 重新握手 + 写审计；viewer 重连 / 配置变更 403
- [ ] 6.2 实现 `/admin/mcp/servers/{id}/reconnect`（触发 mcp 域，写审计，降级不阻断平台）
- [ ] 6.3 Write failing tests: `mcp doctor` 渲染红 / 黄 / 绿清单；认证值脱敏不回明文
- [ ] 6.4 实现 `/admin/mcp/doctor` 诊断入口（消费 mcp doctor，结果经 `_mask`）

## 7. server 接线 + 收尾

- [ ] 7.1 改 `server.py`：mount `connector_admin_api.router`
- [ ] 7.2 全量 `uv run pytest -x -q` 绿
- [ ] 7.3 `uv run ruff format src tests && uv run ruff check src tests && uv run mypy src` 通过
- [ ] 7.4 手动冒烟：列 connector 目录(secret 脱敏)→ 看 (user, connector) 矩阵四态 → 未授权格无代授权入口 → 代 revoke 二次确认写审计 → MCP server 列表降级可见 → 展开看 `server__{tool}` → 手动重连 → mcp doctor 红黄绿脱敏
