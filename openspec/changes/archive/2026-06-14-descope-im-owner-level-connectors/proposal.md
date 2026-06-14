# descope-im-owner-level-connectors

> 删除整套**未实现、空转**的 owner-level IM connector 机制（`im_connectors` 表 + connector_store/manager/config + shim + owner-level admin API/CLI + server 接线）。它仅为 whatsapp 而设，但 whatsapp 无适配器、`ConnectorManager` 以 `factories={}` 实例化（永不启动任何连接器）——纯死脚手架。决定见 [im-access-model](../../../docs/architecture/im-access-model.md) §9（whatsapp v1 缓做、未来增量重建）。**完成 owner→tenant 塌缩第三刀**（owner_id 在 IM 域彻底退役）。
>
> **排序**：build-on `descope-im-channel-allowlist`——**apply 须排其后**（重叠 connector_store/admin_api/__init__；channel-allowlist 先删 im_channel_allowlist 表 + allowlist_enforced 列 + allowlist 代码，本 change 删剩下的 connector 机制）。propose 不冲突（artifacts 独立），故现在写。head 取真实值（channel-allowlist 落地后为 090，本迁移 091，**勿硬编码**）。

## Why

owner-level IM connector 机制（`im_connectors`）现状（审计 + §9 调研 2026-06-14）：
- **无 whatsapp 适配器**（im_gateway/ 只有 slack/telegram）。
- **`server.py` 用 `ConnectorManager(factories={})` 实例化** → `start()` 永远命中 "factory is None → unconfigured"，**从不启动任何连接器**。
- 仅服务 whatsapp 一个平台（`PLATFORM_CONFIG_KEYS` 只有 whatsapp）；slack/telegram 走 per-agent（agent.yaml + supervisors），spec 明示"Slack and Telegram are excluded from the owner-level connector lifecycle"。
- whatsapp 与 slack/telegram 架构差异大（webhook-push / 共享号 / 需路由 / DM-only / 24h+模板，见 §9），未来真做须正经增量设计，现这套空壳给不了头部启动、留着≈零价值。

删整套，零运行时风险（它本就什么都不做）。

## What Changes

- **Alembic 迁移**（append after head、勿硬编码；channel-allowlist 后为 091）：`DROP TABLE im_connectors`。
- **删模块**：`connector_store.py`（im_connectors 的 store）、`connector_manager.py`（惰性 supervisor）、`connector_config.py`（whatsapp 配置 schema/resolve/seed_from_env）、shim `im_connector_store.py` / `im_connector_manager.py` / `im_connector_config.py`。
- **admin API**（`admin_api.py`）：删 owner-level connector CRUD 端点（list/get/create/enable/disable connector）。注：`/allowlist` 端点已由 channel-allowlist 删。
- **CLI**（`admin_cli/im_connectors.py`）：删 connector 管理命令（整文件，allowlist 命令已由 channel-allowlist 删）。
- **`im_gateway_management/__init__.py`**：去 connector_store/manager/config 相关 re-export。
- **server.py**：删 `_connector_manager` 实例化 + `start_all_enabled` 调用 + owner-level connector admin 路由挂载（保留 per-agent slack/telegram supervisor 接线、im 身份 resolver 注入——那是另一套、live）。
- **不碰（铁律）**：per-agent slack/telegram（slack_supervisor/telegram_supervisor/connector_registry/agent.yaml im.*，live）；`oauth-connector-admin`/`connector_admin_api`（工具 OAuth）；`kb_connector*`（KB 数据源）；`im_users`（身份，3b 已瘦身）。
- **文档**：`data-model.md` §3.2 去 `im_connectors`；ER 图删其相关边（`users ..o{ im_connectors`、`im_connectors ..o{ im_channel_allowlist` 后者已随 channel-allowlist 去）。

## Capabilities

### Removed Capabilities
- `im-connector-registry`: owner-level 连接器注册/状态/启停/列举/创建（im_connectors 表）——机制空转、descope。
- `im-connector-config`: owner-level 连接器配置解析/掩码/更新/env seed/凭据 schema——随机制 descope。
- `im-connector-admin-ui`: owner-level 连接器管理控制台——随机制 descope。
- `user-scoped-im-connectors`: per-owner 连接器注册/owner 作用域解析/生命周期/路由/身份/allowlist——owner-level 整套退役（身份已 3b 瘦身、allowlist 已 descope、连接器机制本 change 删）。

## Impact

- **owning package**：`platform`（Alembic + `im_gateway_management/` 的 connector_store/manager/config + shims + admin_api + __init__ + `admin_cli/im_connectors.py` + `server.py` 接线）。
- **public API surface**：移除 owner-level connector 管理端点 + CLI；per-agent slack/telegram 路径不受影响。
- **owned tables**：`DROP im_connectors`。
- **config namespace**：无（whatsapp 配置 schema 随 connector_config 删）。
- **cross-module dependencies**：不碰 agent 零 platform import；不碰 per-agent IM、tool OAuth、KB connector。
- **migration / shim plan**：append after head（channel-allowlist 落地后 091，勿硬编码）；`DROP TABLE im_connectors`；forward-only + downgrade 反向重建空表（数据不复原；pre-launch）。
- **相邻切片**：**apply 排在 `descope-im-channel-allowlist` 之后**（重叠 connector_store/admin_api/__init__，串行；本 change 删 channel-allowlist 删剩的部分）；已核 `knowledge-base-standalone-service` 不碰；apply 前 pull 确认 head + channel-allowlist 已落地。
