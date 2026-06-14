# descope-im-owner-level-connectors Tasks

> **apply 前置**：`descope-im-channel-allowlist` 须已落地 main（重叠 connector_store/admin_api/__init__）。TDD：实现 task 先测试见红→见绿；测试在实现之前。迁移号 append after head、**勿硬编码**。铁律：只删 owner-level connector 机制；不碰 per-agent slack/telegram、tool OAuth、KB connector、im_users。

## 1. 迁移：drop im_connectors（Alembic）

- [x] 1.1 [测试] integration：head 后 `im_connectors` 表不存在（先红）
- [x] 1.2 [实现] 新迁移（append after head、勿硬编码；channel-allowlist 后为 091）：`DROP TABLE im_connectors`；downgrade 反向重建空表（数据不复原）→ 1.1 转绿

## 2. 代码：移除 owner-level connector 机制

- [x] 2.1 [测试] integration：owner-level connector 管理端点（list/get/create/enable/disable connector）404；CLI connector 命令移除；server 启动不再实例化 ConnectorManager / 调 start_all_enabled（先红/现态确认）
- [x] 2.2 [实现] 删 `connector_store.py`、`connector_manager.py`、`connector_config.py` + shim `im_connector_store.py`/`im_connector_manager.py`/`im_connector_config.py`；`admin_api.py` 删 connector CRUD 端点；`admin_cli/im_connectors.py` 删 connector 命令；`__init__.py` 去相关 re-export；`server.py` 删 `_connector_manager` 实例化 + start_all_enabled + owner-level connector 路由挂载 → 2.1 转绿
- [x] 2.3 [测试] integration：**铁律回归**——per-agent slack/telegram 连接/解析/im 身份注入仍正常；tool OAuth（connector_admin_api）、KB（kb_connector）、im_users 未受影响（现态确认）

## 3. 文档 + spec 同步

- [x] 3.1 `docs/architecture/data-model.md` §3.2：去 `im_connectors`；ER 图删 `users ..o{ im_connectors` 等相关边
- [x] 3.2 archive 时同步 delta：REMOVED 整 capability —— `im-connector-registry` / `im-connector-config` / `im-connector-admin-ui` / `user-scoped-im-connectors`

## 4. 收尾

- [x] 4.1 `make test-pr` 全绿；`uv run pytest tests/integration -q`（不带 `-x`）对照 main 基线无新增失败（重点：per-agent IM 路径无回归、启动无 ConnectorManager 报错）
- [x] 4.2 全仓 grep：无残留 `im_connectors`（表）/ `connector_store`(im) / `connector_manager` / `connector_config`(im) 引用（迁移历史/归档除外）；`connector_admin_api`(tool OAuth)/`kb_connector`/`slack_supervisor`/`telegram_supervisor`/`im_users` **完好未误删**
- [x] 4.3 `openspec validate descope-im-owner-level-connectors` 通过；checkbox 全 `[x]`
