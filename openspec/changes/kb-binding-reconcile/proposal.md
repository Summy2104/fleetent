## Why

agent 的 KB 绑定(`agent.yaml` 的 `knowledge.bindings[]`)由 `materialize._knowledge_for_agent` 从管理库 `agent_kbs` 表**一次性** materialize。部署后管理员在 platform bind/unbind 改了 `agent_kbs`,**正在运行的 agent 不会更新**——agent.yaml 快照与 `agent_kbs` drift,必须重新部署或重启才生效。绑定变更对运行中 agent 静默无效。

> 约束:运行时**不能**让 long-term-ctx 直接查 `agent_kbs`(那是 agent→management.db 反向依赖,违反解耦契约——agent 必须能在无 platform DB 环境下跑)。所以唯一正确解是"agent.yaml 快照 + reconcile 刷新",不是"运行时 live 查询"。

## What Changes

- **绑定变更经 reconcile 传播**:platform 在 bind/unbind 改 `agent_kbs` 时 SHALL 触发受影响 agent 的 knowledge 重 materialize 信号(复用既有 `resync_epoch` + node reconcile + home-hash 重写范式,与 skills backflow resync 同构)。
- **node 重 materialize**:node reconcile SHALL 在该信号下从 `agent_kbs` 重新生成 agent.yaml 的 `knowledge.bindings`,更新 agent home。
- **agent 在 session 边界 reload**:agent SHALL 在**下一个 session/对话边界**采用更新后的 bindings,**不**在进行中的对话中途改变 KB 检索范围。
- **单租户不变量显式校验**:agent 的所有 `knowledge.bindings[]` SHALL 共享该 agent 的 `tenant_id`;materialize/load 时 SHALL 校验,违反则 fail loudly(消除 `long_term_ctx` 取 `bindings[0].tenant_id` 的隐含未守护假设)。

不改变:运行时绑定的真相载体仍是 agent.yaml 快照(保解耦);`agent_kbs` 表与 binding 管理 API;long-term-ctx 的注入/预算语义;extraction/检索行为。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `agent-knowledge-config`: 新增"bindings 与 `agent_kbs` 经 reconcile 保持同步、session 边界生效"的要求;新增"所有 bindings 共享 agent tenant_id 的单租户不变量校验"。

## Impact

- **owning packages**:`platform.agent_lifecycle`(materialize)+ `platform.knowledge_base_management`(bind/unbind 触发信号)+ `node`(reconcile 重 materialize)+ `agent_config` / `runtime`(session 边界 reload + 不变量校验)。
- **public API surface**:bind/unbind 路径新增"标记受影响 agent 需 resync"副作用;agent_config 加载新增单租户校验。
- **owned tables**:复用既有 `resync_epoch` 机制;若 knowledge 维度需独立 epoch 列,走 Alembic 管理库迁移(forward-only),否则复用现有信号。
- **config namespace**:无新增。
- **cross-module 依赖**:保持单向 platform→node→agent;agent 仍只读自身 home,不反查 `agent_kbs`(解耦不破)。
- **测试**:integration(bind/unbind 后重 materialize 出新 bindings;agent 在 session 边界采用;跨 tenant binding 被拒)。
