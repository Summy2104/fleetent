# standalone-agent-approval Delta

## ADDED Requirements

### Requirement: approvals 审批人列统一命名与语义
`approvals` 表的审批人列 SHALL 命名为 `approver_user_id`，与 agent 侧其余身份列（`requester_user_id`、`sessions.user_id`、`memory_items.user_id` 等）共用统一语义：存 **Principal.user_id 字符串**——managed 部署为内部 `users.id`、standalone 部署为渠道原生 id、基础设施动作为 `system` 哨兵；无 DB 外键、跨库 opaque。旧列名 `approver_actor` SHALL 经嵌入式 Y 迁移（`RENAME COLUMN`）改名，代码与测试 MUST NOT 再引用旧列名。

#### Scenario: 列名为 approver_user_id
- **WHEN** `agent_state.db` 的嵌入式迁移运行到最新版本
- **THEN** `approvals` 表含 `approver_user_id` 列且不含 `approver_actor` 列

#### Scenario: 旧版本库升级保留数据
- **WHEN** 一个 `approvals.approver_actor` 已填值的旧版本库被 migrate-on-open 升级到最新版本
- **THEN** 该列改名为 `approver_user_id`，历史行的值原样保留

#### Scenario: 代码不再引用旧列名
- **WHEN** 检查 `governance/approval_store.py` 与 `governance/permission_gate.py` 源码
- **THEN** 不存在字符串 `approver_actor`

## REMOVED Requirements

### Requirement: 存量 approvals 表缺 approver_actor 列时 ensure_schema 自愈
**Reason**: `approval_store.py` 的 `ensure_schema` 已由 retire-ensure-schema 系列移除（模块 docstring 明示 "injected via set_state_db() at agent boot — no ensure_schema"），自愈/回填代码不存在，本 requirement 为预存 spec 漂移。
**Migration**: `approvals` 表的 schema 演进统一由 `runtime/agent_state_migrations.py` 的嵌入式 Y（migrate-on-open + `user_version` 版本闸）承担；Y 谱系内的列变更（含本次 `approver_actor → approver_user_id` 改名）以追加迁移版本表达，不再有运行时探测补列路径。Y 版本闸之外的遗留形态库（如曾手动止血的双列形态）不在支持范围。
