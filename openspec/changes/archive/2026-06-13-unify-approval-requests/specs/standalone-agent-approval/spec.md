# standalone-agent-approval Delta

## MODIFIED Requirements

### Requirement: approvals 审批人列统一命名与语义
审批生命周期（含审批人列）SHALL 落在统一的 `approval_requests` 表（`approvals` 表已退役并整体被它取代）。审批人列 SHALL 命名为 `approver_user_id`，与 agent 侧其余身份列（`requester_user_id`、`sessions.user_id`、`memory_items.user_id` 等）共用统一语义：存 **Principal.user_id 字符串**——managed 部署为内部 `users.id`、standalone 部署为渠道原生 id、基础设施动作为 `system` 哨兵；无 DB 外键、跨库 opaque。`/approvals` 端点读写 `approval_requests`（subject_type=`tool_call`）。代码与测试 MUST NOT 再引用已退役的 `approvals` 表或旧列名 `approver_actor`。

#### Scenario: 审批人列在 approval_requests
- **WHEN** `agent_state.db` 的嵌入式迁移运行到最新版本
- **THEN** 不存在 `approvals` 表；`approval_requests` 含 `approver_user_id` 列、不含 `approver_actor`

#### Scenario: 存量 approvals 行迁移保留
- **WHEN** 一个含存量 `approvals` 行（`approver_user_id` 已填值）的旧库被 migrate-on-open 升级到最新版本
- **THEN** 这些行迁入 `approval_requests`（`subject_type=tool_call`），审批人值原样保留，`/approvals` 端点仍可列出/解析

#### Scenario: 代码不再引用退役表/旧列名
- **WHEN** 检查 governance 审批相关源码
- **THEN** 不存在对 `approvals` 表的读写，也不存在字符串 `approver_actor`
