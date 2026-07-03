## Context

托管路径下 MCP server 的配置数据流是单向一条链:前端表单 → `POST/PUT /admin/mcp/servers`(`connector_admin_api.py`)→ `mcp_server_store`(管理库 `mcp_servers` 表)→ `materialize._mcp_servers_for_agent()` 读 store 行拼 `McpServerSettings` → `materialize._mcp_payload_to_map()` 把非默认字段提到 `x-fleetent` 下 → 落 `agent.yaml`。这条链服务 standalone 物化(`materialize_agent_home`)和 node 托管同步(`desired_state_payload_from_agent_file`),没有第二份拷贝。

`x-fleetent` 的 4 个字段在 `config.py::McpServerSettings` 里早有定义(`degrade_mode` / `file_root` / `file_isolation` / `approval_rules`),也已进 `MCP_FLEETENT_EXT_DEFAULTS`(决定哪些字段提到 `x-fleetent` 下)和 `mcp_yaml_field_paths()`(算路径提示)。缺的只是**这条数据链的两端**:store 没有列存它们,前端没有输入框填它们。中间的物化整形逻辑不用动。

`approval_rules` 的语义(`governance/approval_policy.py::_mcp_risk`):每条规则 `{tool, when}`,`when` 为 `null` 时整个工具的每次调用都要审批;`when` 有条件时,只有当**每个**列出参数的调用值(字符串化后)都落在其允许值列表里才要审批(参数间"与"、同参数多值"或")。

## Goals / Non-Goals

**Goals:** 管理员在 MCP server 表单里能查看并编辑全部 4 个 `x-fleetent` 字段,存进平台 DB,经既有物化链路正确落到托管 agent 的 `agent.yaml` 的 `x-fleetent` 块下(含 `approval_rules` 的 `when` 条件)。

**Non-Goals:** 不改 `_mcp_payload_to_map` / `MCP_FLEETENT_EXT_DEFAULTS` / `mcp_yaml_field_paths()` 的整形与路径逻辑;不改审批门的匹配算法;不做 `agent.yaml` 整份实时预览;不按 transport 类型隐藏字段(见 D4)。

## Decisions

**D1 · store 新增 4 列,`approval_rules` 存 JSON,其余存 TEXT。**
`mcp_servers` 表加 `degrade_mode`(TEXT, default `'degrade'`)、`file_root`(TEXT, default `''`)、`file_isolation`(TEXT, default `'on'`)、`approval_rules`(JSON/TEXT, default `'[]'`)。`add_mcp_server` 新增同名 kwarg;`_EDITABLE` 加这 4 个;`approval_rules` 在写入时 `json.dumps`、`_decode` 读出时 `json.loads`(与 `args`/`env`/`headers`/`auth_config` 完全同款);前三者按普通字符串列处理。`_COLS` 追加 4 列,`_select_rows` 沿用既有 "no such column" fallback 惯例对旧库兜底。默认值与 `McpServerSettings` / `MCP_FLEETENT_EXT_DEFAULTS` 保持一致,保证"全默认 → 物化时被 `_mcp_payload_to_map` 丢弃 → `agent.yaml` 不出现 `x-fleetent`"这条既有不变量成立。

`_as_server_config`(供 `resolve_mcp_servers` → 全局 server 运行时注册)也一并带上这 4 字段,避免全局 server 的 `approval_rules` 在运行时注册路径上丢失(半接线的 store 更危险)。

**D2 · admin body 用 `config.py` 的模型校验,不手写校验。**
`McpServerCreateBody` 加 `degrade_mode: str = "degrade"` / `file_root: str = ""` / `file_isolation: str = "on"` / `approval_rules: list[dict[str, Any]] = []`;`McpServerEditBody` 加对应可选字段(默认 `None`,`model_dump(exclude_none=True)` 只透传显式改的)。校验在 body 的 `model_validator` 里做:构造 `McpServerSettings(...)`(或直接 `[McpApprovalRule(**r) for r in approval_rules]`)让 pydantic 抛错,非法 `degrade_mode`/坏 `approval_rules` 结构 → 422。`connector_admin_api.py` import `config`(中立核心)是既有依赖(它已 import `mcp_yaml_field_paths`),不触碰 `materialize`(③ 面),不违反 `test_module_dependency_guardrails`。

> 校验落点选 body 而非 store:store 是"照单落库"的边界层,校验属于 API 入口职责,和现有 `_normalized_auth_config` 同层。

**D3 · materialize 透传,物化整形零改动。**
`_mcp_servers_for_agent()` 构造 `McpServerSettings(...)` 时补:`degrade_mode=row["degrade_mode"]`、`file_root=row["file_root"]`、`file_isolation=row["file_isolation"]`、`approval_rules=[McpApprovalRule(**r) for r in row["approval_rules"]]`。`_mcp_payload_to_map` 遍历 `MCP_FLEETENT_EXT_DEFAULTS` 自动 hoist——无需改动。`_decode` 对旧库缺列时给这 4 个键补默认值(degrade/""/on/[]),确保 `row["..."]` 恒可取。

**D4 · 4 字段一直显示,不按 transport 隐藏。**
`file_root`/`file_isolation` 名义上只对 stdio 的 `/exchange` 桥接有意义,但它们都是 server 级 `x-fleetent` 字段,按 transport 隐藏会引入分支复杂度、且与"字段=配置项"的心智不符。全部常驻显示,和 `degrade_mode`/`approval_rules` 一致。(已与用户确认。)

**D5 · `approval_rules` 前端用"数组中间形状",build 时转 `{tool, when}`。**
表单 state 用便于增删的形状:
```ts
type ApprovalRuleForm = { tool: string; conditions: Array<{ arg: string; values: string[] }> }
```
- `conditions` 为空 → build 出 `{ tool, when: null }`(整工具审批)
- `conditions` 非空 → `when = { [arg]: values }`,build 时丢掉 `arg` 为空或 `values` 全空的条件
- `serverFormFromEditing` 反向:`when` 为 `null`/缺省 → `conditions: []`;`when` 为字典 → 摊平成 `conditions` 数组
`canSubmitServer` 要求每条规则 `tool` 非空;条件里 `arg` 非空时其 `values` 至少一个非空(否则该条件视为未完成,阻止提交或在 build 丢弃——采用"build 丢弃 + 无有效内容的空规则阻止提交"策略,细节在 tasks 里定测试)。路径提示 `approval_rules` 指向整个列表 `mcpServers.<id>.x-fleetent.approval_rules`(field-schema 已产出)。

**D6 · 表单分组为可折叠「fleetent 扩展」小节。**
表单已很长(鉴权类型最多展开 7 个字段)。这 4 个字段归入一个 `<details>`/折叠区,默认折叠,降低视觉噪音;`approval_rules` 编辑器在该区内。纯 UI 归组,不影响数据流。

## Risks / Trade-offs

- **[Alembic 迁移号]** → 本分支基于 origin/main(77cd7ccc)建,已确认 main head=117(skill-gitops 的 115–117 已合入),故本次迁移 `revision = "118"`、`down_revision = "117"`。迁移体照 `109_mcp_auth_config.py` 的 `_has_table` guard + `op.add_column` + `server_default` 写法。
- **[`approval_rules` 三层嵌套编辑器是本次主要复杂度]** → 用 D5 的中间形状把"字典↔有序数组"的转换收敛到 logic 层单测覆盖(尤其空条件 ↔ `when:null` 往返),UI 只做增删行;渲染层测试断言基本结构即可,不追求穷举。
- **[`_as_server_config` 与 `_mcp_servers_for_agent` 两个读取消费者需同时带上新字段]** → 两处都在同一 store/materialize 改动 task 内覆盖,integration 测试各测一条(托管物化 + 全局解析)避免只接一半。
- **[body 校验依赖 `config.py` 模型]** → 若 `McpServerSettings` 校验副作用过重(如 authorization_code 的必填校验),只用于校验 4 个 x-fleetent 字段时可能误伤。缓解:`approval_rules` 单独用 `McpApprovalRule` 逐条校验、枚举字段单独校验,不构造整个 `McpServerSettings`,避免牵连鉴权校验。
