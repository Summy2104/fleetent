## 1. 前置核实（实现前的事实确认，无代码改动）

- [x] 1.1 核实 MCP3 连接健康契约：`mcp_client.HealthState`（`healthy`/`degraded`/`unavailable`，行 49-54）、`get_health`（行 171）按 server 实例持有、`_call_*_tool` 中 `server._health is not HealthState.healthy` 短路返回 `_unavailable_result`（行 851/882）
- [x] 1.2 核实 MCP5 认证不可用契约：`McpServerConfig._auth_unavailable`（行 151）正交于连接健康、由 `_clear_oauth_auth_state` 在重载/重注册清除（行 532）、`_call_http_tool` 中 `auth_type=="oauth2" and _auth_unavailable` 返回认证不可用文本（行 875-879）
- [x] 1.3 核实 `tool_registry.get_schemas()`（行 90-92）当前扁平返回 `_registry` 全部 schema、无可见性过滤；MCP 工具名为 `{server_id}__{tool_name}` 双下划线；确认拟新增的可注入过滤钩子默认 `None` 时与现状/非 MCP 场景零回归
- [x] 1.4 核实 `register_all`（行 461-466）启动失败：`_register_server` 抛出后该 server 不进 `_server_registry`、log warning、不阻断启动（启动失败=工具未注册=天然不可见）

## 2. 统一可用性判定（mcp_client.py，整合 MCP3+MCP5 两正交态）

- [x] 2.1 Write failing tests for `is_server_available`：连接 `healthy` 且认证可用 → True；连接 `degraded`/`unavailable`（任一）→ False；`oauth2` 且 `_auth_unavailable` → False；`none`/`api_key` 服务无认证维度（healthy → True）。按 server 实例读取，无全局可变状态。运行 `uv run pytest -x -q` 看到红
- [x] 2.2 Implement `is_server_available(server)`（逻辑与：连接 healthy AND 非 oauth2-认证不可用），看到绿

## 3. schema 摘除与恢复（tool_registry.py 过滤钩子 + mcp_client 注入）

- [x] 3.1 Write failing tests for 过滤钩子：`tool_registry` 钩子默认 `None` 时 `get_schemas()` 返回全部（现状不回归）；注入按工具名判定的谓词后，不可用 server 的工具 schema 被摘除、其他与非 MCP 工具保留。`monkeypatch` 钩子，看到红
- [x] 3.2 Implement `tool_registry` 可注入 `_schema_visibility_filter` 钩子（默认 `None` 不过滤）与 `get_schemas()` 过滤逻辑（过滤视图，不删 `_registry`），看到绿
- [x] 3.3 Write failing tests for mcp_client 注入：mcp_client 设置钩子为「按工具名解析 `server_id` → 查 `_server_registry` → `is_server_available`」；不可用 server 工具被摘、恢复（健康+认证清除）后同一注册项重新出现在 schema（不重注册）。看到红
- [x] 3.4 Implement mcp_client 侧钩子函数与设置入口（解析 `{server_id}__{tool}`、调用 D1 判定），看到绿

## 4. 降级模式 degrade / strict / silent（McpServerConfig.degrade_mode）

- [x] 4.1 Write failing tests for `degrade_mode` 字段：默认 `degrade`；配置解析 `degrade`/`strict`/`silent`；非法值回退 `degrade` 并 log（不静默、不吞异常）。看到红
- [x] 4.2 Implement `McpServerConfig.degrade_mode` 字段（默认 `degrade`）与加载校验/回退，看到绿
- [x] 4.3 Write failing tests for `degrade` 行为：不可用服务工具被摘、另一可用服务工具与对话正常。看到红
- [x] 4.4 Implement `degrade` 路径（复用 §3 摘除），看到绿
- [x] 4.5 Write failing tests for `strict` 行为：`strict` 服务不可用 → 可被 agent_loop 消费的「strict 不可用」判定为真、以明确错误终止语义；终止范围限绑定该 server 的 agent，不阻断平台/其他 agent。看到红
- [x] 4.6 Implement `strict` 判定入口（查询是否存在 strict 且不可用的 server，供 agent_loop 消费；本 change 不改 agent_loop 业务，仅暴露判定），看到绿
- [x] 4.7 Write failing tests for `silent` 行为：与 `degrade` 同样摘除工具，但仅 log、无面向用户/外部通知。看到红
- [x] 4.8 Implement `silent` 路径（摘除 + 仅 log，不触发通知），看到绿

## 5. register_all 启动失败降级统一

- [x] 5.1 Write failing tests for 启动失败一致性：两个 server 一个启动连接失败 → 平台正常启动、失败 server 工具不出现在 schema、另一 server 工具正常可见。看到红
- [x] 5.2 Write failing tests for `strict` 启动失败：`strict` server 启动失败不阻断平台启动、不牵连其他 server/agent，仅绑定该 strict server 的 agent 运行以明确错误终止。看到红
- [x] 5.3 Implement 启动失败与运行时降级的统一表现（启动失败=未注册=天然不可见；strict 启动失败的判定与 §4.6 同一入口），看到绿

## 6. 降级期调用安全兜底（竞态）

- [x] 6.1 Write failing test for 竞态调用：工具已摘除但基于旧 schema 仍发起调用 → 沿用 MCP3/MCP5 既有短路返回明确不可用结果（连接级/认证级各自文本），不进真实网络/子进程、不裸抛、不卡住，其他服务不受影响。外部 HTTP 用 `respx` mock、stdio 用 `unittest.mock` mock，不发真实请求。看到红/绿确认兜底
- [x] 6.2 Implement（若需）确保 §3 摘除未绕过既有调用短路；不改 MCP3/MCP5 短路逻辑本身，看到绿

## 7. 收尾

- [x] 7.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`），无回归
- [x] 7.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿
- [x] 7.3 `uv run mypy src` 无新增错误
