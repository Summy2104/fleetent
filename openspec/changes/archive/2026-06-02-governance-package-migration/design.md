## Context

当前治理域文件体量不大，但职责集中：

| Legacy file | 当前职责 | 目标模块 |
| --- | --- | --- |
| `permission_gate.py` | 高风险工具审批、默认 permission gate | `governance.permission_gate` |
| `quota.py` | 用户 quota 检查、用量扣减 | `governance.quota` |
| `audit_log.py` | 平台审计事件记录 | `governance.audit_log` |
| `blocklist.py` | 用户封禁 / 解封状态 | `governance.blocklist` |
| `agent_policy.py` | 工具访问策略检查 | `governance.agent_policy` |

这些模块依赖 user store 或被 runtime / platform 调用，但不应该长期留在根目录。相比 runtime 迁移，它们没有 import
副作用注册要求；相比 config / db 迁移，它们的全仓依赖面更小。

## Target Structure

目标结构：

```text
src/fleetent/governance/
  __init__.py
  permission_gate.py
  quota.py
  audit_log.py
  blocklist.py
  agent_policy.py

src/fleetent/permission_gate.py
src/fleetent/quota.py
src/fleetent/audit_log.py
src/fleetent/blocklist.py
src/fleetent/agent_policy.py
```

旧顶层文件只保留 re-export shim。示例：

```python
"""Compatibility shim for governance permission gate."""

from fleetent.governance.permission_gate import PermissionGate, _default_gate

__all__ = ["PermissionGate", "_default_gate"]
```

实际 `__all__` 必须依据原模块 public names 精确生成，不要漏掉测试或调用方依赖的 public API。

## Public API Strategy

新 canonical import 是 `fleetent.governance.*`。

旧 import 路径继续可用：

- `fleetent.permission_gate`
- `fleetent.quota`
- `fleetent.audit_log`
- `fleetent.blocklist`
- `fleetent.agent_policy`

shim 不允许：

- 创建数据库连接。
- 读取配置。
- 承载业务逻辑。
- 定义可变全局状态。

如果原模块存在测试需要 monkeypatch 的常量或对象，优先把测试迁到新 canonical path；不要为了测试便利让 shim 承载状态。

## Data Ownership

本 change 不新增或修改 schema。

迁移后，治理域拥有以下既有数据职责：

- permission gate 的运行期审批状态。
- quota 相关持久化访问。
- audit log 相关持久化访问。
- blocklist 相关持久化访问。

如果这些实现当前复用 `user_store.DB_PATH` 或 legacy store helper，本 change 可以保留该依赖，不在同一 spec 中迁移
database runtime。

## Import Migration

实现迁移后，建议优先更新以下内部 import 到 canonical path：

- `agent_loop.py` 使用 `fleetent.governance.permission_gate` 和 `fleetent.governance.agent_policy`。
- `tool_registry.py` 使用 `fleetent.governance.agent_policy`。
- `user_store.py` 如需调用 blocklist，可使用 `fleetent.governance.blocklist`。

测试可以分两类：

- compatibility tests：证明旧路径仍可 import。
- canonical tests：新测试和新 monkeypatch 使用 `fleetent.governance.*`。

不要求在本 change 中清理所有外部旧 import；shim 的存在就是为了降低迁移冲击。

## Risks

- shim `__all__` 漏掉 public name，导致旧调用方 import 失败。
- monkeypatch 仍打在旧 shim 路径，实际实现已移到新模块，导致测试隔离失效。
- store 层 legacy DB monkeypatch 依赖 `user_store.DB_PATH`，迁移时误改 DB 隔离方式。
- runtime import 顺手改太多，造成非治理域行为变化。

## Verification

必须验证：

- 旧 import 路径仍可用。
- 新 canonical import 路径可用。
- 现有 permission / quota / audit / blocklist / agent policy 行为测试通过。
- module boundary check 通过。
- 完整测试通过。

本 change 是结构迁移，不应改变 CLI、HTTP、IM 或 agent runtime 行为。
