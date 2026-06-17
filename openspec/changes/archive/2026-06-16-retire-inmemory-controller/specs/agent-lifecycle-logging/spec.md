## REMOVED Requirements

### Requirement: agent_lifecycle.controller 记录进程启停事件

**Reason**: `agent_lifecycle/controller.py`（`AgentController`）随进程启停内存 controller 一并删除，其日志要求不再适用。
**Migration**: 进程启停日志移交 node supervisor（C3）侧；platform 不再 spawn/terminate agent 子进程。

### Requirement: agent_lifecycle.api 记录管理 API 调用

**Reason**: `lifecycle_admin_api`（仅含 `/start`、`/stop`、`/runtime-status`）整体删除，其 API 调用日志要求不再适用。
**Migration**: 启停语义改为声明式 status（`agent-lifecycle-toggle` 的审计日志覆盖）；实际态读取经 node 上报（C2）。`agent_lifecycle.materialize 记录物化操作结果` 不受影响、继续保留。
