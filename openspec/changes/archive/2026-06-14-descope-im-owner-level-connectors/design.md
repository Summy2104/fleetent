# 设计：descope-im-owner-level-connectors

## D1 — 死透的证据
- `server.py` `ConnectorManager(factories={})`——空 factory，`start()` 永远 unconfigured，**从不起任何连接器**。
- 无 whatsapp 适配器；`PLATFORM_CONFIG_KEYS` 只有 whatsapp；slack/telegram 明示排除在 owner-level 之外（走 per-agent）。
- 即 im_connectors 表 + 整套机制 = admin 能 CRUD 配置但驱动不了任何东西。

## D2 — 范围边界（铁律）
- **删**：im_connectors 表 + connector_store/manager/config + 3 shim + owner-level admin connector 端点 + CLI + server 接线。
- **不碰**：① per-agent slack/telegram（slack_supervisor/telegram_supervisor/connector_registry/agent.yaml `im.*`/im 身份 resolver 注入）= live，server.py 这部分保留；② `oauth-connector-admin`/`connector_admin_api`（工具 OAuth）；③ `kb_connector*`（KB）；④ `im_users`（身份）。apply 动手前 grep 区分 owner-level connector vs 这四类。

## D3 — 与 channel-allowlist 的关系（build-on，apply-after）
- `descope-im-channel-allowlist`（在跑）删：im_channel_allowlist 表 + im_connectors.allowlist_enforced 列 + allowlist 代码/端点/store 处理。
- 本 change 删：im_connectors 表本体 + connector 机制。**重叠文件**：connector_store.py（channel-allowlist 删其 allowlist_enforced 处理，本 change 删整文件）、admin_api.py（channel-allowlist 删 /allowlist，本 change 删 connector CRUD）、__init__.py（两边各 prune）。
- 故 **apply 串行：channel-allowlist 先**。本 change 基于其落地后状态写（allowlist 已不在；本 change 删 connector 机制）。propose 互不冲突（artifacts 独立）。
- 迁移：channel-allowlist 091？不——channel-allowlist 是 090，本 change 091。本 change 直接 `DROP TABLE im_connectors`（allowlist_enforced 列已由 090 去、或随表整删，皆可）。

## D4 — owner→tenant 塌缩收尾
三刀齐：im_users(3b 删 owner_id)✅ + im_channel_allowlist(channel-allowlist 整删)✅在跑 + im_connectors(本 change 整删)。完成后 owner_id 在 IM 域**彻底退役**，IM 只剩 tenant 一个作用域轴（经 agent.tenant_id / users.tenant_id）。

## D5 — 未来 whatsapp（§9 备忘，非本 change）
真做时增量重建：控制面 webhook 端点 + whatsapp 适配器（电话→NormalizedMessage，chat_type=dm）+ 共享号路由（一号→默认 agent 或菜单）+ 模板/24h 出站。现有 NormalizedMessage + im_users(platform,platform_user_id) + 访问闸 已是够用的扩展缝。
