# 设计：descope-im-channel-allowlist

## D1 — 为什么死透了
- `is_allowed()` 零生产消费方（grep 验证）；入站准入由 agent.yaml `ConnectorAccess`→（IM 访问模型完工后）`im.allow_groups` + chat_type 闸接管。`im_channel_allowlist` 是被取代的旧机制。
- `im_connectors.allowlist_enforced` 唯一作用是 gate 这张表（`channel_allowlist.is_allowed` 读它）；表删→开关悬空。

## D2 — 范围边界
- 删：im_channel_allowlist 表 + channel_allowlist store + shim + admin /allowlist 端点 + CLI + connector_store 的 allowlist_enforced 处理 + __init__ re-export。
- 删 im_connectors 的 `allowlist_enforced` **一列**（它专属于这张 allowlist），**不碰 im_connectors 表本体**（owner 级 whatsapp 模型 §9 另议）。
- 不碰同名无关物：`tool_auto_approvals.is_allowed`（governance 指纹）、`permission_gate` 的 allowlist。

## D3 — 迁移
- append after head（090，勿硬编码）。`DROP TABLE im_channel_allowlist`。`im_connectors` 删 `allowlist_enforced`：SQLite 用 batch 重建（保留 `(owner_id, platform)` UNIQUE + 其余列）或 `ALTER ... DROP COLUMN`。
- downgrade：重建空 im_channel_allowlist + 加回 allowlist_enforced 列（数据不复原；pre-launch 可接受）。

## D4 — owner→tenant 收尾定位
本刀是"owner 塌缩进 tenant"的第二刀：im_users(3b 已删 owner_id)✅ → im_channel_allowlist(本刀，随死表整张去掉 owner_id)→ 剩 im_connectors.owner_id（§9 whatsapp owner-level，待）。三刀齐后 owner_id 在 IM 域彻底退役。
