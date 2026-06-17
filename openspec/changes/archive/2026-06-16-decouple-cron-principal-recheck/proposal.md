## Why

定时任务 fire 时，`cron_scheduler._resolve_cron_principal` 直接调用 `user_store.get_by_id`
去查 platform 的 management 库（`users` 表）做创建者撤权复核（blocked/deleted）。这让
**agent runtime 隐式依赖 platform 的 management 库**——与 `cron-scheduled-tasks` 既有的
「agent-owned，无 platform 依赖」要求相悖。standalone agent 本不该打开 management 库，目前
仅靠 `no such table` 兜底信任 IM 身份才勉强能跑；一旦 `DATABASE_URL` 被误设为空串，
`create_database("")` 抛 `ValueError`（空 scheme，非 `no such table`），落入兜底 `except`
→ fail-closed → **所有带真实用户 id 的定时任务静默跳过、不投递**（开发服已复现）。

## What Changes

- 给 `cron_scheduler` 增加注入缝：模块级 `_principal_resolver`（默认 `None`）+
  `set_principal_resolver(resolver)`，对齐既有 `user_store.set_api_key_resolver` /
  `connectors.set_provider` / `set_im_identity_resolver` 范式。
- `_resolve_cron_principal` 改为：未注入 resolver（standalone）→ **直接信任** task `origin`
  里平台边缘已认证的 IM 身份，**完全不调用 `user_store`、不打开 management 库**；已注入
  resolver（platform）→ 委派给 resolver 执行 `users` 表 blocked/deleted 复核。
- `cron_scheduler` **移除**对 `user_store` 的 import 与直连；查库逻辑迁入 platform 侧注入闭包。
- platform 启动钩子（`server.py` lifespan）调用 `cron_scheduler.set_principal_resolver(...)`
  装入复核实现（与现有三处注入并列）。
- `system` / `default` user_id 的既有短路语义保持不变。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `cron-scheduled-tasks`: 强化「agent-owned，无 platform 依赖」契约，新增对 **fire 时
  principal 解析** 的要求——standalone 下 MUST NOT 打开/查询 platform management 库，须信任
  归档的 IM 身份；platform 的 blocked/deleted 撤权复核须经 `set_principal_resolver` 注入提供，
  而非 agent 侧硬连 `user_store`。

## Impact

- 代码：`src/fleetent/cron_scheduler.py`（`_resolve_cron_principal` 重写 + 新增 seam，移除
  `user_store` import）、`src/fleetent/server.py`（lifespan 注入复核 resolver）。
- public API surface：新增 `cron_scheduler.set_principal_resolver`。
- owned tables：无（无 schema 变更）。
- config namespace：无。
- cross-module dependencies：**移除** `cron_scheduler → user_store` 直连；**新增**
  `platform(server.py) → cron_scheduler` 注入（方向合规，platform 依赖 agent runtime）。
- migration / shim：无。
- 行为：standalone 定时任务不再受空/错 `DATABASE_URL` 影响；platform 撤权语义不变。
- 测试：`tests/unit/test_module_dependency_guardrails.py`（cron 不再依赖 user_store）、
  cron_scheduler 的 principal 解析单测（standalone 信任路径 / platform 注入路径）。
