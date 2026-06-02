## Why

`src/fleetent` 顶层仍有多组 legacy 平铺模块。相比 runtime、platform user center、channels 和
infrastructure，治理域的边界已经比较清楚：权限审批、配额、审计日志、封禁和工具访问策略都属于横切治理能力。

当前这些文件仍平铺在根目录：

- `permission_gate.py`
- `quota.py`
- `audit_log.py`
- `blocklist.py`
- `agent_policy.py`

继续平铺会让 runtime、platform 和 channels 在后续开发时直接触碰治理实现文件，也不利于逐步形成模块化单体的
public API 边界。本 change 只做结构迁移：把治理域实现迁入 `fleetent.governance` package，并保留旧 import
路径 thin shim。

## What Changes

- 新增 `src/fleetent/governance/` package。
- 将治理域实现迁入：
  - `src/fleetent/governance/permission_gate.py`
  - `src/fleetent/governance/quota.py`
  - `src/fleetent/governance/audit_log.py`
  - `src/fleetent/governance/blocklist.py`
  - `src/fleetent/governance/agent_policy.py`
- 将旧顶层文件改为 compatibility shim：
  - `src/fleetent/permission_gate.py`
  - `src/fleetent/quota.py`
  - `src/fleetent/audit_log.py`
  - `src/fleetent/blocklist.py`
  - `src/fleetent/agent_policy.py`
- 保持现有 public API、数据库表、配置和运行时行为不变。
- 增加或调整测试，证明新 package import 和旧 import 路径都可用。
- 更新 source module organization roadmap，记录治理域迁移 spec。

## Out of Scope

- 不修改权限审批语义。
- 不修改 quota 计算语义。
- 不修改 audit / blocklist 的持久化表结构。
- 不新增 Alembic migration。
- 不迁移 `user_store.py`、`api_key_store.py`、`auth.py` 或其他 platform user center 文件。
- 不迁移 `agent_loop.py`、`tool_registry.py`、`tools.py` 等 runtime 文件。
- 不删除旧 import shim。
- 不重命名 public API。

## Module Boundary Impact

- **Owning package**：`governance`。
- **Public API surface**：
  - 新增 canonical import 路径 `fleetent.governance.permission_gate`、`fleetent.governance.quota`、
    `fleetent.governance.audit_log`、`fleetent.governance.blocklist`、`fleetent.governance.agent_policy`。
  - 旧路径 `fleetent.permission_gate`、`fleetent.quota`、`fleetent.audit_log`、`fleetent.blocklist`、
    `fleetent.agent_policy` 保留为 shim。
- **Owned tables**：不新增表；现有 quota、audit、blocklist 相关表 owner 迁移为 `governance`。
- **Config namespace**：无新增配置。
- **Cross-module dependencies**：
  - runtime 继续通过 public API 使用 permission gate 和 agent policy。
  - platform / channels 继续通过 public API 使用 quota、audit、blocklist。
  - governance 可以调用 user store public API 解析用户身份，但不得反向 import runtime entrypoint。
- **Migration / shim plan**：
  - 第一步迁移实现到 `fleetent.governance.*`。
  - 第二步将旧顶层文件改为只 re-export public names 的 thin shim。
  - 第三步更新测试和少量内部 import 到 canonical path；不要求本 change 一次性消除所有旧 import。
