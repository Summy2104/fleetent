# descope-im-channel-allowlist

> 删除已死的 `im_channel_allowlist`（per-owner 渠道准入白名单）及其耦合的 `im_connectors.allowlist_enforced` 开关。它的渠道准入职责已被刚完工的 IM 访问模型（agent.yaml `im.<platform>.allow_groups` 群白名单 + 闸）取代；`is_allowed()` 零生产消费方（已验证）。同时是"owner 塌缩进 tenant"的一刀（去掉这张以 owner_id 作用域的死表）。head=089（新迁移 090，**勿硬编码**）；已核 `knowledge-base-standalone-service` 不碰。

## Why

`im_channel_allowlist`（按 `(owner_id, platform, scope_type, scope_id)` 的渠道/工作区准入白名单）已彻底死：
- `channel_allowlist.is_allowed()` **无任何生产消费方**（grep 排除 tool_auto_approvals / permission_gate / 定义后为空）——入站准入早已走 agent.yaml `ConnectorAccess`，IM 访问模型完工后正式由 `im.allow_groups`（群白名单）+ chat_type 闸接管。
- `im_connectors.allowlist_enforced`（INTEGER 开关）唯一作用是 gate 这张表的 `is_allowed`；表死则它悬空。

删表 + 删悬空开关，零运行时风险。

## What Changes

- **Alembic 迁移**（append after head、勿硬编码）：`DROP TABLE im_channel_allowlist`；`im_connectors` 删列 `allowlist_enforced`（SQLite batch 重建或 DROP COLUMN，保留其余列/UNIQUE）。downgrade 反向重建（空表 + 加回列，数据不复原）。
- **store**：删 `channel_allowlist.py`（add_entry/remove_entry/list_entries/is_allowed）+ 兼容 shim `im_channel_allowlist.py`；`connector_store.py` 去 `allowlist_enforced` 列处理 + `set_allowlist_enforced`。
- **`im_gateway_management/__init__.py`**：去 `channel_allowlist` 及 `add_entry`/`is_allowed`/`list_entries`/`remove_entry`/`set_allowlist_enforced` 的 re-export。
- **admin API**（`admin_api.py`）：删 `/allowlist` 端点（list/add/remove）+ connector 上 upsert 的 `allowlist_enforced` 入参/写入（:72/145-146）。
- **CLI**（`admin_cli/im_connectors.py`）：删 allowlist 相关命令（add_entry 等，:106）。
- **不碰**：`im_connectors` 表本体（owner 级 whatsapp，§9 另议）——只去它的 `allowlist_enforced` 一列；`tool_auto_approvals.is_allowed` / `permission_gate` 的同名 `is_allowed`（无关）。
- **文档**：`data-model.md` §3.2 去 `im_channel_allowlist` + im_connectors 的 allowlist_enforced 注记；ER 图删边 `im_connectors ..o{ im_channel_allowlist`。

## Capabilities

### Removed Capabilities
- `im-channel-allowlist`: 整个 capability 移除（Channel allowlist storage / Per-platform opt-in enforcement / Routing enforces the channel allowlist / Allowlist management surface 四条 requirement）——渠道准入由 IM 访问模型的群白名单接管，本机制 runtime 从不消费。

### Modified Capabilities
- `im-connector-registry`: `im_connectors` 列清单去掉 `allowlist_enforced`（其唯一用途是 gate 已删的 allowlist）。

## Impact

- **owning package**：`platform`（Alembic + `im_gateway_management/channel_allowlist.py`·`im_channel_allowlist.py`·`connector_store.py`·`admin_api.py`·`__init__.py` + `admin_cli/im_connectors.py`）。
- **public API surface**：移除 `/admin/im/.../allowlist` 端点 + connector upsert 的 `allowlist_enforced` 字段；store/CLI allowlist 函数删除。
- **owned tables**：`DROP im_channel_allowlist`；`im_connectors` 删 `allowlist_enforced` 列（其余不动）。
- **config namespace**：无。
- **cross-module dependencies**：不碰 agent 零 platform import；不碰 IM 访问模型（agent.yaml 群白名单是替代者、已落地）。
- **migration / shim plan**：append after head（090，勿硬编码）；DROP TABLE + DROP COLUMN（或 batch 重建 im_connectors 保 UNIQUE）；forward-only + downgrade 反向（数据不复原；pre-launch）。
- **相邻切片**：owner→tenant 收尾还剩 im_connectors（§9 whatsapp owner-level）一刀；已核无 collision；apply 前 pull 确认 head。
