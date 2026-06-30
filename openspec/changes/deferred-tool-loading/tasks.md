## 1. 配置字段：hot_mcp_servers

- [ ] 1.1 写测试：`agent.yaml` 解析 `hot_mcp_servers`（缺省→空列表、给定 fnmatch 模式列表→原样保留）
- [ ] 1.2 实现：在 `agent_config.py` 的 agent 配置 dataclass 新增 `hot_mcp_servers: list[str]`（默认空列表），并接入加载

## 2. 三态划分与词法检索（纯函数，tools/ 内新模块）

- [ ] 2.1 写测试：`is_hot_tool(name, hot_mcp_servers)` —— 内置工具恒 hot；MCP 工具按 `{server}__{tool}` fnmatch 匹配 `hot_mcp_servers` 才 hot；空列表→所有 MCP 非 hot
- [ ] 2.2 实现：`is_hot_tool` / hot 集合计算（区分内置 vs MCP 工具名）
- [ ] 2.3 写测试：词法匹配 `search_deferred(query, candidates)` —— 大小写不敏感 token 计分、名命中权重高于描述、返回 top-N（默认 10）；`select:a,b` 形态精确取名、绕过打分、不存在的名标记未命中
- [ ] 2.4 实现：词法计分 + `select:` 解析 + top-N 截断
- [ ] 2.5 写测试：一行描述提取 `one_line_desc(schema)` —— 取 description 首行、去换行、超长（~80 字符）截断
- [ ] 2.6 实现：`one_line_desc`

## 3. deferred 目录文本构建

- [ ] 3.1 写测试：`build_deferred_catalog(allowed, hot, activated)` —— 仅含「放行 − hot − activated」的工具，每行「name — 一行描述」，被 `allowed_tools` 拒绝/已 hot/已 activated 的工具不出现
- [ ] 3.2 实现：`build_deferred_catalog`（复用 `is_tool_visible` 放行结果 + `is_hot_tool` + activated 集合 + `one_line_desc`）

## 4. tool_search 内置工具

- [ ] 4.1 写测试：`tool_search` 关键词 query → 返回 top-N 完整 schema 文本，并把命中 canonical 名写入 `tool_context.activated_tools`
- [ ] 4.2 写测试：`tool_search` `select:` 精确直选 → 仅返回指定工具 schema；不存在/被拒绝的名不写入 activated、结果中标明未命中
- [ ] 4.3 实现：`tool_search` 工具（声明 `tool_context` 形参，恒 hot，注册进 registry），复用第 2 节检索函数

## 5. ToolContext 与每轮 tools= 组装

- [ ] 5.1 写测试：`ToolContext.activated_tools` 默认空集合、可被 mutate
- [ ] 5.2 实现：`ToolContext` 新增 `activated_tools: set[str]` 字段（默认空集）
- [ ] 5.3 写测试：`_policy_chat` 组装 —— 给定内置 hot + 若干 deferred MCP + activated 集合含 T，结果 `tools=` 恰含「内置 hot + tool_search + T」，不含其它 deferred；既有过滤层（sandbox/outbound/skill/allowed_tools/名投影）对裁剪后集合仍生效
- [ ] 5.4 实现：在 `_policy_chat`（loop.py ~1949 之后）插入 deferred 裁剪步骤（保留 hot + tool_search + activated），其余管线不变
- [ ] 5.5 实现：deferred 目录文本在 run 内构建一次并注入上下文（与系统提示同期）；在两处 run 入口（loop.py ~1994 / ~2576）创建 `ToolContext` 时初始化 `activated_tools`

## 6. 集成验证与收尾

- [ ] 6.1 写集成测试（mock LLM）：配置含 MCP 工具的 agent，首轮 `tools=` 不含 MCP deferred 工具但含目录文本；模型调用 `tool_search` 命中 T；下一轮 `tools=` 含 T 且可调用；同 run 后续轮 T 持续在场
- [ ] 6.2 写集成测试：`hot_mcp_servers: ["crm__*"]` → crm 工具首轮即在 `tools=`、不在目录；其它 server MCP 工具仍 deferred
- [ ] 6.3 运行 `make test-pr` + `uv run pytest tests/integration -q`，对照 main 基线确认无新增失败
- [ ] 6.4 运行 `uv run mypy src` 与 `uv run ruff check src tests` 确认类型与 lint 通过
