> TDD 硬门禁:每个实现 task 先写测试见红,再写实现见绿。后端最窄命令 `uv run pytest <file>::<test> -x -q`;前端 `pnpm --dir frontend vitest run <file>`。测试任务已排在实现之前。

## 1. 迁移 + 绑定 store 的 approval_rules 往返(integration,TDD)

- [x] 1.1 写测试 `tests/integration/`(照既有绑定/store 往返风格,`tmp_path` + `apply_migrations`):迁移到 head 后 `agent_mcp_servers` 有 `approval_rules` 列、`mcp_servers` **无** `approval_rules` 列(PRAGMA 断言);`agent_store` 写入某 (agent, server) 的 approval_rules 后读回为结构化 list;未配时默认 `[]`。先见红。
- [x] 1.2 新建迁移 `migrations/versions/119_mcp_approval_rules_per_agent.py`(`revision="119"`,`down_revision="118"`):`op.add_column("agent_mcp_servers", approval_rules JSON server_default '[]')` + `batch_alter_table("mcp_servers") drop_column("approval_rules")`;downgrade 反向(加回 mcp_servers 列、删 agent_mcp_servers 列)。`agent_store` 加 `get_agent_mcp_approval_rules(agent_id, server_id)` / `set_agent_mcp_approval_rules(...)`(JSON dumps/loads)。跑 1.1 见绿。

## 2. agent 侧 API:GET/PUT approval-rules(integration,TDD)

- [x] 2.1 写测试 `tests/integration/test_agent_admin_api.py`(复用其绑定测试 fixture):`PUT /admin/agents/{name}/mcp/{sid}/approval-rules` 带一条 `{tool, when}` 规则 → 200 且绑定读回;`GET` 返回该规则;未绑定该 server 时 PUT/GET → 404;坏规则(缺 `tool`)→ 422;非 admin PUT → 403。先见红。
- [x] 2.2 在 `agent_admin_api` 加这两个端点(GET `_current_user`、PUT `_require_admin`,校验用 `McpApprovalRule`,校验 helper 放中立处避免跨 face 依赖);PUT 前校验 (agent, server) 已绑定。跑 2.1 见绿。

## 3. 移除服务级 approval_rules(integration/unit,TDD)

- [x] 3.1 改测试:`tests/integration/test_connector_admin_api.py` 里 `test_mcp_admin_api_round_trips_xfleetent_fields`/`..._rejects_invalid_...` 去掉 approval_rules 断言(改为断言 create/edit body **不接受** approval_rules、GET **不返回** approval_rules);保留 degrade/file 字段断言。先见红(实现仍接受时)。
- [x] 3.2 实现:`McpServerCreateBody`/`McpServerEditBody` 删 `approval_rules` 字段及 `_validated_approval_rules` 调用;`GET /mcp/servers` 的 `_from_row` 删 approval_rules;`create_mcp_server` 不再透传;`mcp_server_store`(`_COLS`/`_JSON_COLS`/`add`/`edit`/`_decode`/`_as_server_config`)删 approval_rules。跑 3.1 见绿。

## 4. materialize 从绑定读 approval_rules(integration,TDD)

- [x] 4.1 改/写测试 `tests/integration/test_agent_materialize_export.py`:两个 agent 各绑定同一 server 但配不同 approval_rules → 各自 `agent.yaml` 的 `mcpServers.<id>.x-fleetent.approval_rules` 反映**自己那份**;绑定未配规则 → 该 server 无 approval_rules(其余 x-fleetent 字段仍来自服务定义)。原「approval_rules 来自服务定义」的断言改为「来自绑定」。先见红。
- [x] 4.2 实现:`_mcp_servers_for_agent` 用 `agent_store.get_agent_mcp_approval_rules(agent.id, server_id)` 取规则塞 `McpServerSettings.approval_rules`;degrade/file 仍从服务行读。跑 4.1 见绿。

## 5. 前端:ApprovalRulesEditor 工具名改 combobox(TDD)

- [x] 5.1 combobox 行为(工具名下拉候选来自 probe + 允许自定义输入)并入 task 7.1 的 `mcp-servers-tab.test.tsx`(编辑器只在 agent 标签页复用,无独立 harness),不另开 editor 单测。
- [x] 5.2 实现:`ApprovalRulesEditor` 加 `toolOptions?: string[]` prop,工具名 `<Input>` 换成可输入 combobox(选项 + 自由输入);其余(条件/值编辑)不变。跑 5.1 见绿。

## 6. 前端:服务表单移除审批编辑器(TDD)

- [x] 6.1 改 `server-dialog-logic.test.ts` / `page.test.tsx`:删 approvalRules 相关断言;`buildServerPayload` 不再产出 `approval_rules`;服务表单不再出现审批规则编辑器与其路径提示。先见红。
- [x] 6.2 实现:`server-dialog` 去掉审批规则区块与状态;`server-dialog-logic` 删 `approvalRules`/`buildApprovalRules`/`ApprovalRuleForm` 导出中服务表单用的部分(编辑器组件本身保留供 agent 侧复用);`connectors/api.ts` 的 `McpServerInput`/`Record` 去掉 approval_rules。跑 6.1 见绿。

## 7. 前端:agent MCP 标签页配置审批规则(TDD)

- [x] 7.1 写测试 `mcp-servers-tab.test.tsx`(MSW mock `GET .../mcp/servers/{id}/tools` + `GET/PUT .../agents/{name}/mcp/{sid}/approval-rules`):展开某已绑定 server 的「配置审批规则」→ 出现 `ApprovalRulesEditor`,工具名下拉含 probe 到的工具;加一条规则保存 → 发出正确的 PUT body;打开时回显已存规则。先见红。
- [x] 7.2 实现:`features/agents/api.ts` 加 approval-rules 的 query/mutation + 复用 tools query;`mcp-servers-tab` 每已绑定行加展开配置区,内嵌 `ApprovalRulesEditor`(toolOptions 来自 tools query)。跑 7.1 见绿。

## 8. Change 收尾验证

- [x] 8.1 `make test-pr`(4282 passed, All checks passed,含 `test_module_dependency_guardrails`)+ `make test-integration-ci`(2245 passed / 23 skipped / 0 failed)全绿。
- [x] 8.2 `make test-frontend` 全绿(340 passed,tsc --noEmit 无错,biome lint 干净)。
- [x] 8.3 Playwright 本地核对(真实浏览器)已过:MCP 服务表单只剩 degrade/isolation/file_root、无审批编辑器;agent MCP 标签页对已绑定 server 有「审批规则」入口→对话框内工具名为可输入 combobox;保存后绑定库存 `[{tool: read_file, when: null}]`,物化 agent.yaml 的 `filesystem.x-fleetent.approval_rules` 正是该条(挂在 agent 绑定上)。
- [ ] 8.4 归档前同步 spec(见本 change 的 specs/ 增量)——`opsx:archive` 在功能分支归档。
