## Context

二次 grounding（2026-06-23）校正后的现状：

- **resolve 双端点**：`server.py:537`（平台进程）+ `agent_app.py:676`（agent 进程），都调
  `approval_router.resolve_approval_request`（按 subject_type 分派：tool_call→permission_gate 恢复 run；
  memory_proposal/skill_proposal→reflection apply）。平台端点仅 `tests/unit/test_platform_admin_api_unit.py` 在调，
  无前端/CLI 消费者。
- **reflection 提案路由已存在并复用 ApprovalRouting**：`_notify_pending_proposal`（reflection.py:1247）取
  `active_agent.approval`，用 `tool_name=f"reflection_{domain}_proposal"` 调 `resolve_approvers`（by_tool 覆盖 by_risk）
  + `gate._notify_approvers` 外呼。`_create_proposal_approval_request`（:1652）写 `routing_key=f"reflection_{domain}_proposal"`。
- **粒度问题**：`ProposalDomain = {memory, skill}`。user-memory 维护（mark_stale/rewrite/merge/compact/delete）和
  shared 建议（`suggest_shared_memory_or_kb`）都 `domain="memory"` → 共用 `reflection_memory_proposal`。
- **本人投递缺口**：无 `proposal.user_id` 当 approver 的逻辑；真要 DM 本人需 user_id→渠道地址解析（A4b、本单不做）。

## Goals / Non-Goals

**Goals:**
- A3：平台不再是审批 resolve actor——删 `server.py` resolve 端点，resolution 统一走 agent 侧。
- A4a：memory 域路由 key 按 target 细分，使 user-memory / shared-memory / skill 三类提案可各自配 approver。
- 复用既有 `resolve_approvers` + 外呼投递，零新机制、纯 agent 侧、配置驱动。

**Non-Goals:**
- A4b（user-memory→本人地址自动解析投递）——拆出待设计，挂 node 身份 resolver。
- 不动 tool_call 路由、不动 agent_app resolve 端点、不改 approval_router 分派逻辑。
- 无 DB 迁移、无 schema 改动。

## Decisions

**D1 · A3 删平台 resolve 端点**。移除 `server.py` 的 `@app.post("/approvals/{id}/resolve")` 函数 +
`ApprovalRequest` 模型（确认无其它引用后）+ `from ...approval_router import resolve_approval_request`（若仅此处用）。
平台 console 保留只读投影（`list_approvals` / get 不动）。落地前 `grep -rn "approvals/.*resolve"` 复核无新消费者；
连带删/改 `tests/unit/test_platform_admin_api_unit.py` 中针对 `server.resolve_approval` 的用例。
agent 侧 `agent_app.py:676` 端点是唯一保留的 resolve HTTP 入口。

**D2 · A4a 路由 key helper**。新增纯函数
`_proposal_routing_key(domain: ProposalDomain, action: str | None) -> str`：
```
skill                                  -> "reflection_skill_proposal"
memory + action=="suggest_shared_memory_or_kb" -> "reflection_shared_memory_proposal"
memory + 其它                          -> "reflection_user_memory_proposal"
```
`_create_proposal_approval_request` 与 `_notify_pending_proposal`（含 `_schedule_pending_proposal_notification`）
各增 `action` 入参（调用点已持有 proposal.action），内部用该 helper 算 routing key / tool_name，替换原
`f"reflection_{domain}_proposal"`。**单一 helper、两处共用**，避免两处漂移成不同 key。

**D3 · 配置语义（行为变更，非代码 alias）**。reflection 提案的 by_tool 配置 key 改为三个细分名；
旧 `reflection_memory_proposal` 不再命中。by_risk medium/high 兜底逻辑不变（仍按 `resolve_approvers` 顺序：
by_tool 命中则用，否则落 by_risk）。这是有意的配置层 breaking——reflection 审批路由尚属新生、无存量依赖，
不留 alias 以免长期歧义；在 proposal/spec 显式声明。

**D4 · user-memory 本单的归宿**。本单 user-memory 提案路由到 `reflection_user_memory_proposal`，由 agent.yaml
配置该 key 的 approver（运营者可先配成本人地址，或配 team 兜底）。"自动解析本人地址并投递" = A4b，明确不在本单。

## Risks / Trade-offs

- **A3 破坏性删端点**：理论上是 public HTTP 移除。已 grep 确认无前端/CLI，唯一消费者是单测。风险低，但须在落地时
  再次 grep 复核（含 openapi 客户端、admin 前端若有）后再删。
- **A4a 配置 breaking**：配过旧 key 的 agent.yaml 会静默落到 by_risk 兜底或无 approver（默认 on_no_approver=reject）。
  reflection 审批路由是新生功能、预计无存量配置；仍在 spec/proposal 显式声明，避免"悄悄不命中"。
- **routing key 取值散落**：必须收敛到单一 `_proposal_routing_key` helper，notify 与 create 两处共用同一函数，
  否则两处算出不同 key → 通知发给 A、台账记 B。测试需断言"同一 proposal 两处 key 一致"。
- **action 透传**：`_create_proposal_approval_request` / `_notify_pending_proposal` 多一个 `action` 参数；
  确保所有调用点（706 user-memory / 970 shared / 992 skill）都传对 action，skill 路径可传 None（不影响 skill key）。
