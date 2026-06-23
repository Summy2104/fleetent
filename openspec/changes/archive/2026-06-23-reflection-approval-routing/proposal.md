## Why

车道 A 收尾的审批归属两件事，二次 grounding 后定案为 A3 + A4a（A4b 拆出待设计）：

1. **平台仍是审批 actor（A3）**：`server.py:537` 暴露 `POST /approvals/{id}/resolve`，调 `resolve_approval_request`
   按 subject_type 路由**所有类型**（含 `memory_proposal`/`skill_proposal`）。这与 agent 拥有审批门、平台只读下游投影
   的原则冲突，也与 `approval-request-lifecycle` spec "MUST NOT 存在两个平行 resolve 入口"的精神相悖
   ——agent 已有 `agent_app.py:676` 的 resolve 端点（合法的 agent 侧通道），平台这条 HTTP 入口无清晰正当用途
   （grep 确认仅 1 个单测在用、无前端/CLI 消费者）。

2. **reflection 提案 approver 路由粒度不够（A4a）**：路由机制其实**早已存在并复用 `ApprovalRouting`**
   ——reflection 用合成 `tool_name=f"reflection_{domain}_proposal"`（domain ∈ {memory, skill}）走
   `resolve_approvers(by_tool/by_risk)` + `gate._notify_approvers` 外呼。但 **user-memory 维护与 shared 建议
   都是 `domain="memory"`**，共用唯一 key `reflection_memory_proposal` → 无法按车道 A 既定规则
   （user-memory→本人 / shared→team 审批人）分别指派。

现在做：删平台 resolve 入口（A3，纯收敛），并把 memory 域路由 key 按 target 细分（A4a，让三类提案各自可配 approver）。
两者强耦合、同在 reflection/governance/agent_config 一带，合成一个 change。

## What Changes

- **A3 · 删平台 resolve 端点**：移除 `server.py` 的 `POST /approvals/{id}/resolve`（及其 `ApprovalRequest` 模型、
  `resolve_approval_request` import，若无其它用途）。所有 resolution 统一走 agent 侧 `agent_app` 的 resolve 端点；
  平台 console 对审批保持**只读投影**（list/get，不 resolve）。连带删/改唯一依赖它的单测。
- **A4a · memory 域路由 key 细分**：reflection 提案的 routing key 由
  `reflection_{domain}_proposal` 细分为：
  - `skill` → `reflection_skill_proposal`（不变）
  - `memory` + `action=suggest_shared_memory_or_kb` → `reflection_shared_memory_proposal`
  - `memory` + 其它（user-memory 维护）→ `reflection_user_memory_proposal`

  细分发生在 routing key 的两个生成处（`_create_proposal_approval_request` 的 `routing_key` +
  `_notify_pending_proposal` 的 `tool_name`），各透传 `action` 或预算好的 key。复用现成 `resolve_approvers`
  + 外呼投递，纯 agent 侧、配置驱动。

**行为变更（须在 design/迁移说明里点出）**：旧 by_tool key `reflection_memory_proposal` 不再被 reflection 提案命中
（改用两个细分 key）；by_risk 兜底不变。现有 agent.yaml 若配过 `reflection_memory_proposal` 需改用新 key。

**明确不做（A4b，拆出待设计）**：真正的"user-memory→本人 DM 投递"需 `user_id→渠道地址`解析，跨进程、agent 不能读平台
绑定表、须挂 node 身份 resolver——单独设计。本单 user-memory 路由停在"可配置 approver 地址"（先配本人地址或 team 兜底）。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `approval-request-lifecycle`: 在"统一审批路由按主体类型分派 resolve"需求中明确 resolve **HTTP 入口仅在 agent 侧**、
  平台不暴露 resolve 端点（只读投影）；并补充 reflection 提案的 approver 路由按 **域 + 目标**细分（user-memory /
  shared-memory / skill 三个 routing key）。

## Impact

- **owning package**：`reflection/`（routing key 生成）、`governance/`（approval_router resolve 入口）、
  `platform/`（server.py 删端点）、`runtime/agent_app`（保留唯一 resolve 端点）
- **public API surface**：移除 `server.py` 的 `/approvals/{id}/resolve` HTTP 端点（破坏性，但无外部消费者）；
  reflection routing key 取值变更（`reflection_user_memory_proposal` / `reflection_shared_memory_proposal` 新增、
  `reflection_memory_proposal` 不再使用）
- **owned tables**：`approval_requests`（routing_key 列写入值变化，无 schema 改动）、`reflection_proposals`（无改动）
- **config namespace**：`agent.approval.by_tool`（agent.yaml）下使用新的 reflection routing key（既有命名空间、无新增）
- **cross-module dependencies**：reflection → `resolve_approvers`/`gate._notify_approvers`（既有）；
  无 agent→platform 反向依赖；A3 删除的是 platform 自己的端点，不影响 agent 侧
- **migration / shim**：无 DB 迁移。配置层 routing key 重命名为行为变更（文档说明），不提供 alias
- **受影响代码**：`src/fleetent/server.py`、`src/fleetent/reflection/reflection.py` + 相关单测
  （`tests/unit/test_platform_admin_api_unit.py` 的 resolve_approval 用例、reflection 路由相关单测）
