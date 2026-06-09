## Context

减法审计经 4 个 Explore agent 核实(2026-06-09),两处确认死实体/死代码:

- **askit 任务队列三表**：`grep` 全 `src` 对 `askit_tasks`/`askit_task_logs`/`askit_workspaces` **零 .py 命中**,仅 `src/fleetent/__pycache__/askit_task_store.cpython-312.pyc` 孤儿字节码;`platform/askit_console/agent_apply_api.py` 只用 `agent_store`/`agent_admin_store`/`audit_log`,不碰这三表;migration 025 建表后无任何读写。
- **KB binding 死代码**：`bind_agent_to_kb`/`unbind_agent_from_kb` 公开导出在代码库无调用点;`retrieval/scope.py` 与 `bindings.py` 重复实现同一组 binding 读取函数。

本变更是 `chore` 性质的删除,无行为变更(除 schema 去表)。

## Goals / Non-Goals

**Goals：**
- 移除 askit 任务队列三表(Alembic down 迁移)。
- 移除未被调用的 KB binding 死导出。
- 收敛 `scope.py`/`bindings.py` 的重复 binding 读取实现为单一来源。

**Non-Goals（明确排除）：**
- **不动** `connectors.agent_id`：它是 specced-但-未实现的 `agent-scoped-connectors`(OAuth 侧),删它=产品决策,另议。
- **不动** `users.api_key`/`_get_by_legacy_key`：单机鉴权唯一非-platform 回落路径,归 #4 Identity 端口。
- 不改 `knowledge_base_agent_bindings` 表本身(它与 `agent_kbs` 的收敛是 R1a 的设计题,本次只清死代码、不动表结构)。

## Decisions

**D1：用新增 down 迁移删表,不回退/改写 migration 025。** 保持迁移链 append-only(符合 persistence-hygiene 的迁移卫生)。新迁移 `drop_table` 三张表;`downgrade()` 重建(可参考 025 的列定义)以保证可逆。

**D2：去重方向 = `bindings.py` 为单一来源,`scope.py` 复用它。** retrieval 侧 `scope.py` 删除重复实现,改 import `bindings.py` 的读取函数(核实其当前是逐字复制)。保持 retrieval 行为不变。

**D3：删死导出前先确认无调用。** 移除 `bind_agent_to_kb`/`unbind_agent_from_kb` 的公开导出前,在 `src` + `tests` 内再次 grep 确认零引用(测试若引用则一并清理或确认是仅测该死代码的测试)。

## Risks / Trade-offs

- **[迁移可逆性]** → `downgrade()` 必须能重建三表,空库 `upgrade head`→`downgrade`→`upgrade` 往返通过。
- **[scope.py 去重引入行为差异]** → 去重后跑 KB 检索相关测试(retrieval/scope),确认 binding 解析行为逐字一致。
- **[死导出其实被外部/测试用]** → D3 的二次 grep 兜底;若有"仅测死代码"的测试,随之删除并在 PR 说明。
- **[孤儿 .pyc]** → 删 `__pycache__/askit_task_store.*.pyc`;若无对应 .py,确认不是误删了在用源码(已核实无 .py 源)。
