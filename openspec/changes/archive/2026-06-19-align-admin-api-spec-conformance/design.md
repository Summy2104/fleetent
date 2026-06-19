## Context

`add-platform-admin-apis` 已落地 main。归档时部分 spec 被软化以匹配实现的 200 / 裸 409。本 change 把更正确的 REST 语义与可运维性收紧回来。approver 路由与 shared-memory actor 在权威 spec 中已与实现对齐，不在范围。

## Goals / Non-Goals

**Goals:** 把 create→201、无体删除→204、注销冲突 409 列出被 pin agent 收紧到 spec 并修正实现与测试。

**Non-Goals:** 不改端点功能（除状态码与 409 体）；不碰 approver/actor（已对齐）；不新增端点。

## Decisions

### D1：收紧而非接受现状

归档软化后，spec 与代码"不矛盾但都不够好"。选择**收紧**：201/204 是 create/无体删除的正确语义，409 列 pin 列表是运维必需（否则不知先解除谁）。比"接受 200 现状"更对，代价仅是改几个状态码与一处 409 体。

### D2：409 体形状

注销冲突时，`node_admin_api` 捕获 `node_store.deregister_node` 的冲突，调 `placement_store.list_by_node(node_id)` 取被 pin agent id 列表，放入 409 detail（如 `{"detail": "...", "pinned_agents": [...]}`）。

### D3：测试同步

把现有断言 `== 200` 改为 201/204；注销冲突测试补断言 409 体含 `pinned_agents`。

## Risks / Trade-offs

- **[状态码改动]** 200→201/204 对正常处理 2xx 的客户端无影响；当前这些端点无外部消费方（CLI 走各自 store）。
- **[409 多一次查询]** 仅冲突路径触发，可忽略。
