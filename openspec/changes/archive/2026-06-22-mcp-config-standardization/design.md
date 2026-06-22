## Context

fleetent 当前 MCP server 配置是私有 `list-of-id`(`mcp_servers: [{id, transport, ...}]`),运行时工具名硬编码 `{server_id}__{tool_name}`(`integrations/mcp/client.py:_make_tool_name`),审批 `governance/approval_policy._mcp_risk` 靠 `name.partition("__")` 切出 server/tool 匹配 `approval_rules`。

经调研:**MCP 协议不规定配置文件格式,也不规定工具名命名空间前缀**(transport 仅 stdio/Streamable HTTP;工具名格式见 open proposal SEP-986)。事实标准是 Claude Desktop 起源的 `mcpServers` map,被 claude-code/opencode/openclaw/Hermes 一致采用;最权威的工具名约定是 `mcp__{server}__{tool}`(双下划线、无歧义)。fleetent 是唯一用 list-of-id 的,工具名 `{server}__{tool}` 也与各平台不一致。

约束:agent/platform 严格解耦(`integrations/` MUST NOT import platform;platform 仅经 agent.yaml/.env 连接;agent 须能 `fleetent agent run` 独立运行)。

## Goals / Non-Goals

**Goals:**
- MCP 配置 drop-in:标准 `mcpServers` map 块可原样粘贴运行。
- 保留 fleetent 全部特性(degrade_mode / 沙箱 `/exchange` / 自托管 OAuth / per-tool 审批),经 `x-fleetent` 扩展块承载。
- 工具名可按目标平台投影,声明式模板,新增平台零代码。
- 审批/访问控制在任何 `tool_naming` 下行为不变(安全不回归)。
- 纯 agent 侧改动,解耦零破坏,性能无可测影响。

**Non-Goals:**
- 不保留旧 list-of-id 兼容(clean cutover,生产手动迁移)。
- 不改平台 DB/admin 路径(`mcp_server_store`/`connector_admin_api`/`mcp_runtime`)——留作后续。
- 不做配置双向导出(只吃标准、不导出标准)。

## Decisions

**D1. 配置外形:标准 `mcpServers` map(替代 list-of-id)。** 备选:保留 list / 双向导入。选 map 因其是事实标准、可粘贴;且 MCP 无官方格式可违反。顶层同时认 `mcpServers`/`mcp_servers`;transport 自动判定(`command`→stdio,`url`→remote)。

**D2. fleetent 扩展走嵌套 `x-fleetent` 块(OpenAPI 厂商扩展惯例)。** 备选:平铺同级字段。选嵌套因标准核心区保持纯净/可粘贴,符合规范的工具忽略未知 `x-` 键;治理/沙箱/OAuth 字段清晰隔离。

**D3. 工具名投影 = 声明式模板(替代固定 enum)。** 备选:固定 enum(claude/hermes/...)。选模板因「加平台 = 加一行配置」而非「加一个代码分支」;预设词是内置模板别名,另留自定义 `{template, sanitize, max_len}` 逃生口。默认 `claude`(`mcp__{server}__{tool}`):最权威、双下划线无歧义。

**D4. 投影 = LLM 边界 in/out 翻译,registry 始终 canonical(关键安全决策)。** 备选:直接按投影名注册工具。**后者会造成审批绕过**——`approval_policy.partition("__")` 在 `mcp__github__create_issue` 上切出 server=`mcp`(错),在单下划线 `mcp_github_create_issue` 上根本不识别为 MCP → `approval_rules` 失配 → 返回 none → 该审批的外发/MCP 操作放行。故投影只在「出 schema / 入 tool_use」两个边界发生,dispatch/risk/permission_gate/allowed_tools/trace/防循环全程见 canonical,行为逐字不变。

**D5. 审批改读 `(server_id, raw_tool)` 元数据(根因加固)。** 注册 MCP 工具时把 `(server_id, raw_tool)` 存入 registry 元数据;`approval_policy` 读元数据判 MCP 风险,**不再 `partition("__")` 切字符串**。这样无论工具名投影成什么格式,审批匹配都正确。

**D6. 反查表 = agent 进程内瞬态,活在 `integrations/mcp`。** 注册期(启动 / tools-list-changed)构建 `投影名→(server_id, raw_tool)` dict,缓存复用;不落库、不持久、platform 不参与。守住解耦 + 独立运行;性能上仅注册期一次构建 + 每工具调用一次 dict 查找,不在流式热路径,微秒级可忽略。

**D7. Clean cutover(无兼容 shim)。** agent.yaml 是 DB 物化产物(`materialize_from_store` 在 create/update 时重写),非用户长期资产;故同时改 parser + materializer + `.example`,旧格式不再解析,生产由运维手动迁移。

## Risks / Trade-offs

- **BREAKING:配置外形 + 默认工具名都变** → 缓解:clean cutover;`materialize` 在 agent create/update 已自动重渲染;`.example` 同步;运维手动迁移存量 standalone agent.yaml 及 skill 内工具名引用。
- **单下划线预设(hermes/opencode)有歧义** → 缓解:反查表精确还原,**绝不对投影名做字符串切分**;治理绑 canonical 元数据(D5),与投影格式无关。
- **工具名 64 字符上限**(`mcp__` 前缀 + 长 server/tool 名可能超限) → 缓解:模板支持 `max_len`(截断/哈希策略)。
- **`x-fleetent` 仅 fleetent 识别**,别家工具忽略 → 这是预期(opt-in 扩展);标准核心区在别处仍可用。
- **投影错误实现会绕过审批** → 缓解:D4/D5 钉死边界 shim + 元数据;**测试强制**:每种 `tool_naming` 下 approval_rules 仍命中、permission_gate 仍拦截(防回归核心用例)。

## Migration Plan

1. 同一改动内改:`config.py`/`agent_config.py`(解析新格式)+ `materialize.py`(渲染新格式)+ `integrations/mcp`(投影 + 元数据)+ `approval_policy`(读元数据)+ `agent.yaml.example`。
2. 部署后,平台侧 agent create/update 自动按新格式重渲染 agent.yaml;运维对存量/手写 standalone agent.yaml 手动迁移,并把 skill 内旧工具名 `{server}__{tool}` 改为新默认 `mcp__{server}__{tool}`(或设 `tool_naming: bare` 维持旧名)。
3. 回滚:revert 本 change(纯代码,无 DB 迁移)。

## Open Questions

- 平台 DB/admin 路径与 `x-fleetent`/投影的对齐(让 admin 也能配 4 特性 + 命名)——**本轮显式不做**,后续单独立项评估是否加 DB 列与 admin UI。
