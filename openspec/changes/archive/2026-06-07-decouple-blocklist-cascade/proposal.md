## Why

`governance/blocklist.py` 当前直接 `import fleetent.platform`（`api_key_store` 吊销密钥、`im_gateway_management` 禁用 IM 账号），违反 CLAUDE.md「Agent / Platform 解耦」中 governance 属 agent-runtime、MUST NOT import `fleetent.platform` 的规则。这是该规则下「现存待审计」依赖中尚未处理的最后一处，挡住了后续的 CI import 守卫。

## What Changes

- 将 admin 级联编排 `block_user` / `unblock_user` / `batch_block` 从 `governance/blocklist.py` 搬到新模块 `platform/user_management/block_service.py`——这些操作本就协调 platform stores（API 密钥、IM 账号），归属 platform 层。
- `governance/blocklist.py` 收窄为「注册封禁存储」：保留 `is_registration_blocked`（agent 侧 `user_store` 注册时读）、`blocked_registrations` 表与 `_init_db`；将原私有 `_ban_registration` 提升为 public `ban_registration` 供 platform 编排调用。结果 governance/blocklist **零 platform import**。
- 调用方 `platform/user_management/user_admin_api.py` 改调 `block_service` 而非 `blocklist`。
- 行为不变：级联效果、unblock 不复活密钥、batch 共享 id、注册封禁拦截均与现状一致——这是模块边界重构，非行为变更。

## Capabilities

### New Capabilities
<!-- 无新增 capability；本变更是模块边界重构 -->

### Modified Capabilities
- `module-boundaries`: 新增「agent-runtime 模块 MUST NOT import platform」要求，把 CLAUDE.md 的解耦规则固化进 spec，并以 blocklist 级联为场景。
- `user-blocklist`: 明确「级联编排归 platform、注册封禁存储 agent 可读」的模块归属拆分（行为要求不变，新增归属约束）。

## Impact

- 代码：`src/fleetent/governance/blocklist.py`（收窄）、新增 `src/fleetent/platform/user_management/block_service.py`、`src/fleetent/platform/user_management/user_admin_api.py`（改调用）。
- 测试：`tests/integration/test_blocklist.py`（改为调 `block_service`，`is_registration_blocked` 仍走 `blocklist`）、`tests/unit/test_governance_imports.py`（更新 blocklist 公共 API 枚举）。
- 无 schema 变更、无 API 行为变更、无新依赖。`blocked_registrations` 表 owner 仍是 governance。
