## Context

`approval_rules` 目前(上一个 change 落地)存在 `mcp_servers`(服务定义表)、经 MCP 服务表单编辑、由 `materialize._mcp_servers_for_agent` 从服务行读出塞进 `McpServerSettings`,再由既有 `_mcp_payload_to_map` 提到 agent.yaml 的 `x-fleetent.approval_rules`。运行时 `governance/approval_policy` 按 server_id 读该 agent.yaml 里的规则判定审批。

绑定关系存在 `agent_mcp_servers`(agent_id, server_id, created_at, created_by, enabled[043], headers[044])——**该表已是「每绑定配置」的既有载体**。agent 侧绑定 API 在 `agent_admin_api`(`GET /admin/agents/{name}/mcp` 列表、`POST/DELETE /admin/agents/{name}/mcp/{server_id}` 绑/解绑)。前端 agent 详情有 MCP 标签页(`features/agents/mcp-servers-tab.tsx` + `features/agents/api.ts`),目前是「服务目录 + 每行绑定开关」。服务工具列表经 `GET /admin/mcp/servers/{id}/tools`(实时 probe)取得。

## Goals / Non-Goals

**Goals:** `approval_rules` 变成 per-(agent,server) 绑定级配置,在 agent 的 MCP 标签页按已绑定服务配置,工具名从该服务实时工具列表选择(取不到可手填),物化进该 agent 自己的 `agent.yaml`。

**Non-Goals:** 不改 `agent.yaml` 的 `x-fleetent.approval_rules` 形状与 `approval_policy` 匹配逻辑;不动 `degrade_mode`/`file_root`/`file_isolation`(仍服务级);不迁移旧的服务级 approval_rules 数据(无正式数据);不改工具 probe 端点本身。

## Decisions

**D1 · `approval_rules` 落 `agent_mcp_servers`,从 `mcp_servers` 移除。**
`agent_mcp_servers` 加 `approval_rules`(TEXT/JSON, server_default `'[]'`),与 `headers` 同款 JSON 序列化。`mcp_servers` 删 `approval_rules`。理由:审批是 per-agent 策略,绑定表本就承载每绑定配置(enabled/headers),单一数据源。Alembic 119(down_revision 118):加绑定列 + 删服务列;downgrade 反向。**不迁移旧数据**——上一个 change 刚上线无正式数据,且服务级规则→哪些 agent 无清晰映射,强迁反而制造噪音;若真有全局默认需求,由 `approval_policy._BUILTIN_MCP_RULES` 承担(不受本次影响)。

**D2 · materialize 从绑定读 approval_rules,与服务定义 merge。**
`_mcp_servers_for_agent(agent)` 对每个已绑定 server:`degrade_mode`/`file_root`/`file_isolation`/其余仍从 `mcp_server_store.get_mcp_server` 的服务行读;`approval_rules` 改从 `agent_store` 的该 (agent, server) 绑定读。构造 `McpServerSettings(approval_rules=[McpApprovalRule(**r) for r in binding_rules])`。既有 `_mcp_payload_to_map` 不变——非默认才 hoist 到 x-fleetent。**每个 agent 的 agent.yaml 只反映自己那份绑定规则**,天然隔离。

**D3 · agent 侧 API:`GET/PUT /admin/agents/{name}/mcp/{server_id}/approval-rules`。**
GET 返回该绑定的 `approval_rules`(未绑定→404);PUT body `{approval_rules: [...]}`,写入前用 `config.McpApprovalRule` 逐条校验(缺 `tool`/`when` 非字典→422),校验 helper 从 `connector_admin_api` 挪到中立处(或复制到 agent 侧,避免 ②控制 face 交叉)。鉴权:GET 用 `_current_user`(viewer 可看)、PUT 用 `_require_admin`,与该文件既有绑/解绑一致。**只有已绑定的 server 才能配规则**(PUT 前校验绑定存在)。

**D4 · 工具名 combobox:下拉 + 允许自定义。**
前端 `ApprovalRulesEditor` 的工具名从 `<Input>` 改为可输入下拉(combobox):`toolOptions` 由调用方传入。agent 标签页配置某 server 规则时,用 `useMcpServerToolsQuery(serverId)` 拿工具名列表当选项;probe 连不上/返回空/用户想填未来才有的工具→仍可手填任意值(combobox 的自由输入)。服务未连通只降级为「没有候选项、纯手填」,不阻断配置(对应用户选定的兜底策略)。

**D5 · 组件搬迁与复用。**
`ApprovalRulesEditor`(`features/mcp/dialogs/approval-rules-editor.tsx`)是纯受控组件,搬到可被 agent 标签页复用的位置(或留原位、agent 侧 import),加一个 `toolOptions?: string[]` prop。`server-dialog` 去掉该编辑器与 `approvalRules` 表单态、payload、校验;`server-dialog-logic` 的 `approvalRules`/`buildApprovalRules` 相应删除。agent 标签页新增「展开配置审批规则」区(每已绑定 server 一份),内嵌该编辑器 + 保存(调 PUT)。

## Risks / Trade-offs

- **[删 118 刚加的 `mcp_servers.approval_rules` 列]** → 迁移紧跟其后,forward-only 无碍;downgrade 完整恢复。风险仅限「已在服务级配过规则的环境」丢配置——本仓库无此数据(仅 dev)。
- **[工具 probe 依赖服务在线]** → 已由 combobox 自由输入兜底(D4);不因 probe 失败卡住配置。
- **[校验 helper 归属]** → `_validated_approval_rules` 现在 connector 侧;agent_admin_api(①管理 face)不应反向依赖 connector。放到中立模块(如 `config.py` 旁的纯函数)或在 agent 侧薄封装 `McpApprovalRule` 校验,避免跨 face 依赖(实现时以 `test_module_dependency_guardrails` 为准)。
- **[前端组件搬迁面]** → 服务对话框与 agent 标签页两处都改;用组件级测试各自覆盖(服务表单不再出现审批编辑器;agent 标签页出现且工具名是 combobox)。
