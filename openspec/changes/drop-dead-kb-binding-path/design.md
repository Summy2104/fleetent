## Context

3a 后深核实 agent↔KB 绑定数据流（data-model §4-④）：`agent_kbs` 是活的唯一真相源且已经 materialize 进 `AgentKnowledge`、被 `long_term_ctx` 消费；`knowledge_base_agent_bindings`（alembic 012）无任何写入点、`resolve_agent_kb_ids` 无活调用方——是死路径。但 `knowledge-base` / `long-term-ctx` 两个 spec 仍把死路径写成现行设计。本 change 删死路径并把 spec 校正到已落地的 `AgentKnowledge` 模型。

约束：管理库表 drop 走 alembic；不得 import platform；统一经 `db.py` 边界。

## Goals / Non-Goals

**Goals:**
- 删死表 `knowledge_base_agent_bindings` + 死代码（`bindings.py` / `retrieval/scope.py` 解析路径）。
- 把 `knowledge-base`、`long-term-ctx` spec 校正到 `agent_kbs → AgentKnowledge` 模型。
- 处理两个自测死路径的测试。

**Non-Goals:**
- 不动 `agent_kbs`（活真相源）、`agent_kbs_store`、`materialize._knowledge_for_agent`、`long_term_ctx` 读 `agent.knowledge` 的现行实现——它们已是正确行为。
- 不涉及 #3 路由 / 物理库（与持久层 #3 解耦）。

## Decisions

**D1 删而非保留死路径。** `knowledge_base_agent_bindings` 无写入、`resolve_agent_kb_ids` 无活调用方 → 删除消除「重复绑定」假象与未来误用。
- 备选：留作"将来可能用"。否决——无写入的孤儿表 + 无调用的解析器是纯负债；真要 agent 侧绑定解析，活路径（agent_kbs→AgentKnowledge）已覆盖。

**D2 spec 校正到 `AgentKnowledge` 模型，不是反向让代码迁回 resolve。** 现行活路径（agent_kbs → materialize → agent.knowledge → long_term_ctx）就是目标态；stale spec 跟随它。
- 备选：把代码改回 spec 描述的 resolve 路径。否决——那是开倒车到死孤儿。

**D3 drop 表走 alembic。** `knowledge_base_agent_bindings` 是管理库 alembic-owned（012），按双权威规则其生命周期归 alembic。

## Risks / Trade-offs

- **误删了实为活路径的东西**（万一有我没查到的写入/调用）。→ 缓解：动手前第一个测试**断言该表生产无写入路径、`resolve_agent_kb_ids` 无 src 活调用方**（仅 export/test）；红→绿确认后再删。
- **spec REMOVED 丢上下文**。→ 缓解：REMOVED requirement 写明 **Reason**（迁到 AgentKnowledge 模型）+ **Migration**（指向 `kb-agent-binding` + `long-term-ctx`）。
- **删 export 破坏 import**。→ 缓解：跑既有 KB / long-term-ctx 单测 + 层边界脚本确认无残留引用。

## Migration Plan

- 新增 alembic 迁移 drop `knowledge_base_agent_bindings`（无数据迁移——本就空）。
- 删死代码 + 调整两个自测；spec delta 随分支归档同步。
- 回滚：未上线、表无数据，回滚 = revert 分支 / 反向迁移。
