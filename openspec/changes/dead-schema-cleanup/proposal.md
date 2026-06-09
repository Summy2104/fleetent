## Why

数据/实体减法审计(2026-06-09)经代码核实,确认两处**死实体/死代码**——技术上零检索/零业务依赖,删除无功能影响:

- **askit 任务队列三表** `askit_tasks` / `askit_task_logs` / `askit_workspaces`:由 migration 025 创建,但**无任何 .py 源使用**(仅剩孤儿 `.pyc`),`askit_console/agent_apply_api.py` 也不碰它们。它们是 apply-API 模型之前的旧"直写 SQLite 任务队列"残留——而 `fleetent-apply-api` spec 已确立"部署仅经 apply API、fleetent 是唯一写者",这套队列表已被取代。
- **KB binding 死代码**:`knowledge_base.bind_agent_to_kb` / `unbind_agent_from_kb` 公开导出**全代码库无人调用**;`knowledge_base/retrieval/scope.py` 与 `knowledge_base/bindings.py` 存在**重复实现**(同样的 binding 读取函数)。

清理它们缩小实体集与代码面,降低后续 #2/#3 持久层重构的噪声。

## What Changes

- **删除 askit 任务队列三表**:新增一条 down 迁移移除 `askit_tasks` / `askit_task_logs` / `askit_workspaces`;确认无源码/测试引用。
- **删除 KB binding 死导出**:移除未被调用的 `bind_agent_to_kb` / `unbind_agent_from_kb` 公开 API。
- **KB binding 读取去重**:把 `scope.py` 与 `bindings.py` 重复的 binding 读取实现收敛为单一来源,行为不变。
- 在 `fleetent-apply-api` 增加一条契约:**系统不维护服务端 askit 任务队列表,agent 部署唯一经 apply API**,把上述清理固化为行为约定。

> **明确不在本次范围**：
> - `connectors.agent_id` 列(及 `agent-scoped-connectors` 能力):它是 **specced 但 OAuth 侧未实现**的能力,删它=产品决策"放弃 agent-scoped OAuth 连接器",留作单独的产品判断。
> - `users.api_key` legacy 列:`_get_by_legacy_key` 是 `authenticate()` 唯一不依赖 platform 的回落路径,删它会切断单机鉴权回落——**归 #4 Identity 端口**统一处理。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `fleetent-apply-api`: 新增一条 requirement——系统不维护服务端 askit 任务队列/工作区表,agent 部署唯一经 apply API(把 askit 死表移除固化为契约)。

## Impact

- **迁移**：新增一条 Alembic 迁移 drop `askit_tasks`/`askit_task_logs`/`askit_workspaces`(migration 025 的逆操作)。
- **代码**：`src/fleetent/knowledge_base/__init__.py`(移除死导出)、`knowledge_base/bindings.py` 与 `knowledge_base/retrieval/scope.py`(去重收敛);删除孤儿 `__pycache__/askit_task_store.*.pyc`。
- **风险**：极低——均为核实过的死实体/死代码;删除后既有测试须保持全绿(无行为变更)。
- **不涉及**：connectors / users / 任何 agent 运行时数据表。
