# kb-agent-binding Specification

## Purpose
TBD - created by archiving change 2026-06-02-knowledge-base-management. Update Purpose after archive.
## Requirements
### Requirement: KB to Agent binding matrix
The system SHALL persist KB↔Agent bindings in an `agent_kbs` table scoped by (tenant_id, kb_id, agent_id), and SHALL expose binding management from exactly two views: the KB detail view (`/admin/kb/{kb_id}/agents`) and the agent detail view (`/admin/agents/{name}/kbs`). No third reverse-lookup endpoint SHALL exist. The agent→KB reverse view SHALL exclude bindings whose KB is archived (callers see only live KBs for the agent). Bindings SHALL be admin-only to change and viewer-readable.

#### Scenario: Bind a KB to an agent
- **WHEN** an admin binds kb_id "support" to agent "support-bot"
- **THEN** the binding is persisted in `agent_kbs` and an audit entry (`kb_bind_agent`) is written

#### Scenario: View bindings from both sides
- **WHEN** an admin or viewer opens a KB's binding list or an agent's KB list
- **THEN** the consistent set of (kb_id, agent_id) bindings for the current tenant is shown

#### Scenario: 反查视图排除已归档 KB
- **WHEN** 从 agent 侧视图（`/admin/agents/{name}/kbs`）读取该 agent 绑定的 KB 列表，且其中某 KB 已归档
- **THEN** 返回列表排除已归档 KB（只列 live KB），与原 `by-agent` 端点行为一致

#### Scenario: 无第三反查端点
- **WHEN** 审视 KB / agent 管理 API 的路由
- **THEN** 不存在 `/admin/kb/by-agent/{agent_id}`（已退役）；agent→KB 反查唯一入口为 `/admin/agents/{name}/kbs`

#### Scenario: Unbind is audited
- **WHEN** an admin removes a KB↔Agent binding
- **THEN** the binding is deleted and an audit entry (`kb_unbind_agent`) is written

#### Scenario: Viewer cannot change bindings
- **WHEN** a viewer attempts to bind or unbind
- **THEN** the request returns 403

### Requirement: Binding relation backs scope limiting and delete protection
The `agent_kbs` binding relation SHALL serve as the authoritative source for long-term-ctx to limit recall to the agent's bound kb_ids, and SHALL back KB archive/delete binding protection. The management plane maintains the bindings only; injection and token-budget semantics belong to long-term-ctx.

#### Scenario: Bound KBs are queryable per agent
- **WHEN** long-term-ctx requests the kb_ids bound to a given agent in a tenant
- **THEN** the binding store returns the agent's bound, non-archived kb_ids

#### Scenario: Bindings drive archive protection
- **WHEN** a KB has at least one row in `agent_kbs`
- **THEN** an archive attempt on that KB is blocked and the binding agents are listed

### Requirement: agent_kbs 以 agents.id 为键且引用完整
`agent_kbs` 复合键中的 `agent_id` SHALL 为整数 `agents.id`（INTEGER），并 SHALL 声明 FK→`agents.id` ON DELETE CASCADE。所有写入/查询路径（KB 侧 `/admin/kb/{kb_id}/agents`、agent 侧 `/admin/agents/{name}/kbs`、materialize 的 `list_kbs_for_agent`）SHALL 以整数 `agents.id` 为键，MUST NOT 以 `str(agent.id)` 或 agent name 寻址。binding 管理行为（绑定/解绑/双向查看/删除保护/审计）不变。

#### Scenario: agent_id 为整数且带 FK
- **WHEN** 管理库迁移运行到最新版本
- **THEN** `agent_kbs.agent_id` 为 INTEGER，且存在 FK→`agents.id` ON DELETE CASCADE

#### Scenario: agent 删除级联清理绑定
- **WHEN** 一个有 KB 绑定的 agent 被删除
- **THEN** 其 `agent_kbs` 行随 FK ON DELETE CASCADE 一并删除，不留孤儿

#### Scenario: 按整数 id 查询绑定
- **WHEN** long-term-ctx / materialize 请求某 agent 绑定的 kb_ids
- **THEN** 以整数 `agents.id` 查询 `agent_kbs`，返回该 agent 的 kb_ids（行为与改前一致，仅键类型规整）

### Requirement: 绑定物化产出可用的 http provider
当 agent 存在至少一条 KB 绑定，且平台已配置 `Settings().kb_serve`（`url` 与 `service_key_ref` 均非空）时，agent 物化（materialize）SHALL 在 agent.yaml 的 `knowledge` 段产出 `provider: {type: "http", url: <kb_serve.url>, auth_ref: "env:FLEETENT_KB_SERVICE_KEY"}`。平台未配置 kb_serve（任一字段为空）时，物化 SHALL 保持既有行为（provider 缺省 local），且 MUST NOT 因此失败。agent 无任何 KB 绑定时，`knowledge` 段行为不变（不启用、不写 provider）。

#### Scenario: 绑定且 kb_serve 已配置时物化 http provider
- **WHEN** agent 在 `agent_kbs` 有绑定，且平台 `Settings().kb_serve.url` 与 `service_key_ref` 均已配置，触发物化
- **THEN** 物化产物 agent.yaml 的 `knowledge.provider` 为 `type: http`、`url` 等于 `kb_serve.url`、`auth_ref` 为 `env:FLEETENT_KB_SERVICE_KEY`，且 `enabled: true`、bindings 与绑定表一致

#### Scenario: kb_serve 未配置时保持 local 且不失败
- **WHEN** agent 在 `agent_kbs` 有绑定，但平台未配置 `kb_serve.url`（或 `service_key_ref` 为空），触发物化
- **THEN** 物化成功完成，`knowledge.provider` 保持缺省（local），与本变更之前的行为一致

#### Scenario: 无绑定时 knowledge 段不启用
- **WHEN** agent 在 `agent_kbs` 无任何绑定，触发物化
- **THEN** `knowledge` 段保持不启用，不含 provider 接线（与既有行为一致）

### Requirement: KB service key 经 desired-state secrets 下发
node desired-state 的 per-agent secrets 装配 SHALL 为被 agent.yaml 引用（经 `collect_env_var_names` 收集，含 `auth_ref: env:` 形式）的 `FLEETENT_KB_SERVICE_KEY` 回填平台解析 `kb_serve.service_key_ref` 所得的 key 值；per-agent 显式 secret（`agent_secrets`）SHALL 优先于平台回填。平台解析 ref 失败（如 env 缺值）时 SHALL 跳过回填并记录 warning，MUST NOT 使该 agent 的 desired-state 组装整体失败。不引入 `referenced_env_names` 之外的第二种 secret 判定口径。

#### Scenario: 绑定 agent 的 desired-state 携带 KB key
- **WHEN** 某 managed agent 物化出 `auth_ref: env:FLEETENT_KB_SERVICE_KEY`，node 拉取 desired-state
- **THEN** 该 agent 的 `secrets` 载荷含 `FLEETENT_KB_SERVICE_KEY`，值为平台解析 `kb_serve.service_key_ref` 的结果；node 依既有流程落盘 `.env`，自愈门禁判定满足，不产生自愈循环

#### Scenario: per-agent 显式 secret 优先
- **WHEN** 管理员已通过 agent secrets 通道为该 agent 显式设置 `FLEETENT_KB_SERVICE_KEY`
- **THEN** desired-state 下发的是显式设置的值，平台回填不覆盖它

#### Scenario: 平台解析 ref 失败时舱壁化降级
- **WHEN** `kb_serve.service_key_ref` 指向的 env 在平台进程缺值
- **THEN** 该 env 名的回填被跳过并记录 warning，desired-state 响应正常返回其余 secrets

#### Scenario: agent 侧检索经下发的 key 认证成功
- **WHEN** agent 以物化的 http provider 配置启动，`.env` 含下发的 `FLEETENT_KB_SERVICE_KEY`，对绑定 KB 发起检索
- **THEN** `HttpKnowledgeProvider` 以 `Bearer <key>` + ingress principal 调 kb serve `/search` 并获得本租户结果

