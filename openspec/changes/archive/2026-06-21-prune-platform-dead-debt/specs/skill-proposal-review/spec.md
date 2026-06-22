## REMOVED Requirements

### Requirement: Approve proposal

**Reason**: 技能提案审批已改为 **agent-owned**：agent 主动经 DM 外呼审批人，平台只读下游投影。平台侧 `POST /admin/skills/proposals/{id}/approve` 当前即返回 409 桩（"approval is agent-owned and delivered via DM"），从不写入。该 requirement 与现实矛盾，是 stale 规格。

**Migration**: 提案审批经 agent 的 DM 审批流完成；平台保留只读的提案列表（inbox）与 diff 查看。`POST /admin/skills/proposals/{id}/approve` 端点移除。

### Requirement: Reject proposal

**Reason**: 同上——拒绝亦为 agent-owned、经 DM 完成；平台侧 `POST /admin/skills/proposals/{id}/reject` 是 409 桩，从不写入。

**Migration**: 提案拒绝经 agent 的 DM 审批流完成；平台保留只读的提案列表与 diff。`POST /admin/skills/proposals/{id}/reject` 端点移除。
