## Why

`agent-definition` spec 早已把身份模型定清：`agents.id`(INTEGER)=不可变身份/平台关系 FK 键，`agents.name`=可读标签、runtime identity（"Runtime agent resolution is file-sourced" 要求 runtime identity SHALL be its name）。v37 迁移 `finalize-agent-identity` 也据此把 `traces.agent_id` 列改名 `traces.agent_name`。

但**收尾没做完**：agent 侧多处进程内载体与路径参数仍叫 `agent_id` 却实装 agent name——`AgentSnapshot.agent_id`、`CommandContext.agent_id`、`ModelPolicySnapshot.agent_id`（均装 name、纯内部消费、不出 wire），以及 `paths.tenant_agent_home_dir/tenant_agent_data_dir`、`tenant_router.agent_scope` 的参数 `agent_id: str`（实收 name 作路径键，符合布局决策 F）。这种"命名撒谎"正是让人误判"身份模型跑偏"的根源（一次审计就据此误报了多条 HIGH 假 bug）。

架构约束不可改：standalone/file agent 的 `agent.yaml` **没有 int id**，解耦契约要求 agent 能在无 platform / management.db 不存在下运行，故 **agent 侧只能用 name 当身份**；平台关系层用 int id（已干净）。因此修的是**代码诚实度**，不是架构——让符号名与既有 spec 一致，堵住再漂移。

## What Changes

- 把上述**实装 name 的字段/参数** `agent_id` → `agent_name`（纯内部符号重命名，无 wire / API / 序列化契约变更；已核实三对象均不出 wire）：`runtime/snapshot.py` 的 `AgentSnapshot`、`im_gateway`+`runtime/commands.py` 的 `CommandContext`、`model/resolver.py` 的 `ModelPolicySnapshot`；`paths.py` 与 `tenant_router.py` 的路径/scope 参数。
- 修唯一一处平台 store 键不一致：`agent_store.set_im_capabilities` 由按 `name` 改为按 `agent.id`（与所有兄弟 store 变更函数一致），调用点 `agent_admin_api` 相应先 `_require_agent(name)→agent.id`。
- 修 `platform/read_projection.py:124` 语义错位（参数名叫 `agent_id` 实传 `agent_name`）。
- 对齐文档 `docs/architecture/agent-home-layout.md`：布局图 25-28 行写 `(tenant, id)` 与 ledger F 的 `<name>` 自相矛盾，统一表述为 **name 作路径键**。

**不做**：磁盘目录键从 name 改 int id（B 方案，被解耦契约否决——standalone 无 id）；KB 队列死回落清理（#1）；by-agent 反查合并（#2）——后两者另立小 change。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `agent-definition`: 收紧"平台关系键挂 id 不挂 name"的契约范围至 **store 写/查键**（锚定 `set_im_capabilities` 修复）；并补充"agent 侧进程内运行时载体承载的 agent 身份值 SHALL 为 name（与文件产物一致），载体字段命名 SHALL 反映其为 name 而非 id"，防止再度回潮。

## Impact

- **代码**（纯内部符号，无行为变更）：`runtime/snapshot.py`、`runtime/commands.py`、`im_gateway/normalizer.py`、`model/resolver.py`、`paths.py`、`tenant_router.py`、`platform/agent_store.py`、`platform/agent_management_console/agent_admin_api.py`、`platform/read_projection.py`。
- **测试**：上述模块的单元测试断言字段/参数名更新；`set_im_capabilities` 调用契约测试。
- **文档/spec**：`docs/architecture/agent-home-layout.md` 措辞对齐；`agent-definition` spec delta。
- **无迁移、无 DB schema 变更、无 API/wire/序列化契约变更、无跨模块依赖方向变更**（仅内部重命名 + 一处 store 键从 name→id）。
- 兼容性：`set_im_capabilities` 若被外部按 name 调用需同步（仓库内唯一调用点是 `agent_admin_api`，一并改）。
