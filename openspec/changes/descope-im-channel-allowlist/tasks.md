# descope-im-channel-allowlist Tasks

> TDD：实现 task 先测试见红 → 实现见绿；测试在实现之前。迁移号 append after head、**勿硬编码**。只删 im_channel_allowlist + im_connectors 的 allowlist_enforced 一列；不碰 im_connectors 表本体、不碰同名无关 is_allowed（tool_auto/permission_gate）。

## 1. 迁移：drop im_channel_allowlist + im_connectors.allowlist_enforced（Alembic）

- [ ] 1.1 [测试] integration：head 后 `im_channel_allowlist` 表不存在；`im_connectors` 无 `allowlist_enforced` 列、其余列 + `(owner_id, platform)` UNIQUE 保留（先红）
- [ ] 1.2 [实现] 新迁移（append after head、勿硬编码）：`DROP TABLE im_channel_allowlist`；`im_connectors` 删 `allowlist_enforced`（batch 重建保 UNIQUE 或 DROP COLUMN）；downgrade 反向（重建空表 + 加回列）→ 1.1 转绿

## 2. 代码：移除 allowlist store / 端点 / CLI / enforced

- [ ] 2.1 [测试] integration：`/admin/im/.../allowlist` 端点 404；connector upsert 不再接受/写 `allowlist_enforced`；connector listing 不含该字段（先红）
- [ ] 2.2 [实现] 删 `channel_allowlist.py` + shim `im_channel_allowlist.py`；`connector_store.py` 去 `allowlist_enforced` 列处理 + `set_allowlist_enforced`；`admin_api.py` 删 `/allowlist` 端点（list/add/remove）+ upsert 的 allowlist_enforced 入参/写入；`__init__.py` 去相关 re-export；`admin_cli/im_connectors.py` 删 allowlist 命令 → 2.1 转绿
- [ ] 2.3 [测试] integration：IM 入站准入仍正常（由 agent.yaml im.allow_groups + 闸接管，不依赖已删 allowlist）——现态确认无回归

## 3. 文档 + spec 同步

- [ ] 3.1 `docs/architecture/data-model.md` §3.2：去 `im_channel_allowlist`；im_connectors 注记去 `allowlist_enforced`；ER 图删边 `im_connectors ..o{ im_channel_allowlist`
- [ ] 3.2 archive 时同步 delta：`im-channel-allowlist`（REMOVED 整 capability）、`im-connector-registry`（storage 列去 allowlist_enforced）

## 4. 收尾

- [ ] 4.1 `make test-pr` 全绿；`uv run pytest tests/integration -q`（不带 `-x`）对照 main 基线无新增失败（重点：IM 连接器 CRUD/状态不受影响、入站准入无回归）
- [ ] 4.2 全仓 grep：无残留 `im_channel_allowlist` / `channel_allowlist` / `allowlist_enforced` 代码引用（迁移历史/归档除外）；`tool_auto_approvals.is_allowed` / `permission_gate` 的 is_allowed **完好未误删**
- [ ] 4.3 `openspec validate descope-im-channel-allowlist` 通过；checkbox 全 `[x]`
