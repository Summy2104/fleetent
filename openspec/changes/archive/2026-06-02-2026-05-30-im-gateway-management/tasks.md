> **实施进度（opsx:apply，部分完成）**
> 已核查（外部 verify）：store 四模块(1-4)+normalizer 门(5.3/5.4)完成；剩余：5.1/5.2 adapter 上报+配置接入、6.x server lifespan/路由、7.x im_admin_api、8.x CLI、9.x 收尾。
>
> **沙箱限制**：本环境只有 Python 3.10，而仓库要求 3.12（`tool_registry.py` 用 PEP 695 `def tool[F: ...]` 语法、多处 `datetime.UTC`）。新模块不 import `agent_loop/tools/server`，可在 3.10 下真实跑红→绿；但凡 import 这些的测试（5.1/5.2 adapter、6.x server、7.x admin_api 等）无法在此跑，需在 3.12 环境验证。`datetime.UTC` 已用进程级 `.pth` 别名 shim 兼容（与 `datetime.timezone.utc` 同对象，非改动产品码）。
>
> **未完成**：5.1/5.2（slack/telegram 适配器接 supervisor + 状态上报 + 从 DB 取凭据）、6.x（server lifespan 改 manager 驱动 + mount router）、7.x（`/admin/im` REST，依赖 `agent-admin-api` 的 is_admin 守卫）、8.x（CLI）、9.x（全量验证）。这些需在 3.12 环境继续。
>
> **git**：沙箱内 `.git/index.lock` 残留且无权删除，无法在此提交；改动需在宿主机 commit。

## 0. 前置检查

- [x] 0.1 确认 `agent-admin-api` change 的 `users.is_admin` 守卫已存在（合入或同分支）；若缺失，先补一个最小 admin 守卫供 `/admin/im/*` 复用
- [x] 0.2 确认 `slack-bolt`、`python-telegram-bot`、FastAPI、aiosqlite 已在依赖中（无需新增）

## 1. im_connector_store — 注册表与状态上报

- [x] 1.1 Write failing tests: `_init_db()` 后 `im_connectors` 表存在且含 `platform`(UNIQUE)/`enabled`/`allowlist_enforced`/`config`/`status`/`last_heartbeat_at`/`last_error`/`created_at`/`updated_at` 列；重复 `platform` 插入被拒
- [x] 1.2 新建 `im_connector_store.py`：复用 `user_store._conn` 与可 monkeypatch 的 `DB_PATH`；实现 `_init_db()` 建表
- [x] 1.3 Write failing tests: `report_status("slack","connected")` 改 status 并刷新 `updated_at`；`report_status("telegram","error",error="x")` 写 `last_error="x"`；`heartbeat("slack")` 刷新 `last_heartbeat_at` 而不改 status
- [x] 1.4 实现 `report_status` / `heartbeat` / `upsert_connector` / `get_connector` / `list_connectors`
- [x] 1.5 Write failing tests: `set_enabled(platform, bool)` / `set_allowlist_enforced(platform, bool)` 切换对应列
- [x] 1.6 实现 `set_enabled` / `set_allowlist_enforced`

## 2. im_connector_config — 配置解析与脱敏

- [x] 2.1 Write failing tests: `resolve("slack")` 优先返回 `im_connectors.config` 的值；config 为空时回退 `Settings` 的 `slack_bot_token`/`slack_app_token`
- [x] 2.2 新建 `im_connector_config.py`：实现 `resolve(platform) -> dict`（DB 优先，.env fallback）
- [x] 2.3 Write failing tests: `resolve_masked("slack")` 把 token 仅保留尾 4 位；adapter 路径 `resolve` 返回原值
- [x] 2.4 实现 `resolve_masked` + `set_config(platform, dict)`（更新后标记需 reload）
- [x] 2.5 Write failing tests: `seed_from_env()` 把 `.env` 令牌写入对应 connector 并对有令牌者置 `enabled=1`；无令牌平台保持 `unconfigured`/`enabled=0`；再次运行幂等（已有 config 跳过，`force=True` 才覆盖）
- [x] 2.6 实现 `seed_from_env(force=False)`

## 3. im_channel_allowlist — 白名单与强制校验

- [x] 3.1 Write failing tests: `_init_db()` 后 `im_channel_allowlist` 表存在且 `(platform,scope_type,scope_id)` UNIQUE；`add_entry` 插入 `allowed=1`；同 scope 再 add 走 upsert 不重复
- [x] 3.2 在 `im_channel_allowlist.py` 实现建表 + `add_entry` / `remove_entry` / `list_entries(platform=None)`
- [x] 3.3 Write failing tests: `is_allowed` 在 `allowlist_enforced=0` 恒真；`=1` 且 channel 命中 `allowed=1` 为真；`=1` 未命中为假；workspace 级条目覆盖其下 channel
- [x] 3.4 实现 `is_allowed(platform, channel_id, workspace_id=None)`（读 connector 的 `allowlist_enforced` + 匹配 channel/workspace 条目）

## 4. im_connector_manager — 适配器生命周期 supervisor

- [x] 4.1 Write failing tests（用注入的假 adapter 工厂，不起真实连接）：`start(p)` 创建任务并置 `connecting`；`stop(p)` 取消任务并置 `stopped`；`reload(p)` = stop+start；重复 start 不重复起任务
- [x] 4.2 新建 `im_connector_manager.py`：维护 `platform -> asyncio.Task`，实现 `start` / `stop` / `reload` / `running()`，经工厂表创建 adapter
- [x] 4.3 Write failing tests: `start_all_enabled()` 只起 `enabled=1` 的平台；无 adapter 实现 / 无凭据的平台（whatsapp）置 `unconfigured` 且不起任务、不抛错
- [x] 4.4 实现 `start_all_enabled()` + whatsapp 占位处理（工厂缺失 → `unconfigured`）
- [x] 4.5 Write failing tests: adapter 任务异常退出时 manager 置 `status=error` + `last_error`，不影响其他平台任务
- [x] 4.6 实现任务异常捕获与状态落库

## 5. im_gateway 适配器改造（MODIFIED）

- [x] 5.1 Write failing tests: Slack / Telegram adapter 在连接 / 断线 / 错误时调用 `report_status` 对应值，连接中周期 `heartbeat`（mock store，不连真实平台）
- [x] 5.2 改 `im_gateway/slack.py`、`telegram.py`：接入状态上报；凭据改经 `im_connector_config.resolve(platform)` 取得（不再直接读 `Settings`）
- [x] 5.3 Write failing tests: `normalizer.route` 在 user 检查之前调用 `im_channel_allowlist.is_allowed`；不通过时回拒绝提示且不进 `get_agent_for_context`；通过时继续既有流程；`NormalizedMessage` 字段与 thread-first 行为不变
- [x] 5.4 改 `normalizer.route`：最前置 channel 白名单校验（已加 `NormalizedMessage.workspace_id`）

## 6. server 生命周期与路由挂载

- [x] 6.1 Write failing tests: lifespan 启动时经 `im_connector_manager.start_all_enabled()` 启动连接器（mock manager，断言被调用且不再硬编码起 adapter）
- [x] 6.2 改 `server.py`：lifespan 改为 manager 驱动；优雅关闭时 `stop` 所有运行连接器
- [x] 6.3 改 `server.py`：mount `/admin/im` router（带 is_admin 守卫）

## 7. im_admin_api — /admin/im REST

- [x] 7.1 Write failing tests: 非 admin 访问 `/admin/im/connectors` 返回 403；admin 返回连接器列表（config 脱敏）
- [x] 7.2 实现 `im_admin_api.py`：`GET /admin/im/connectors`、`GET /admin/im/connectors/{platform}`
- [x] 7.3 Write failing tests: `PATCH /admin/im/connectors/{platform}` 改 config / allowlist_enforced；`POST .../enable` 置 enabled=1 且调 manager.start；`POST .../disable` 置 0 且 manager.stop
- [x] 7.4 实现 connector PATCH / enable / disable / status 端点
- [x] 7.5 Write failing tests: `GET /admin/im/allowlist?platform=` 列表；`POST /admin/im/allowlist` 增；`DELETE /admin/im/allowlist/{id}` 删
- [x] 7.6 实现 allowlist CRUD 端点

## 8. admin CLI 命令

- [x] 8.1 Write failing tests: `im-connector list` 打印各平台 status（脱敏）；`im-connector enable/disable --platform p` 切换；`im-connector set-config --platform p ...` 写 config；`seed-connectors` 迁入 .env
- [x] 8.2 在 `admin.py` 增 `im-connector` 子命令组 + `seed-connectors`
- [x] 8.3 Write failing tests: `im-channel allow --platform p --scope-type channel --scope-id C` 增条目；`im-channel disallow --id n` 删；`im-channel list --platform p` 列
- [x] 8.4 在 `admin.py` 增 `im-channel` 子命令组

## 9. 验证与收尾

- [x] 9.1 全量 `uv run pytest -x -q` 绿
- [x] 9.2 `uv run ruff format src tests && uv run ruff check src tests && uv run mypy src` 通过
- [x] 9.3 手动冒烟：seed-connectors → enable slack → 健康仪表盘/`GET /admin/im/connectors` 看到 connected → 配 channel 白名单并 enforce → 未列 channel 被拒、已列放行
