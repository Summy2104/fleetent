## Why

MCP3（mcp-health-reconnect，已设计）建立了**连接级**健康状态机：每个服务持有 `HealthState`（`healthy` / `degraded` / `unavailable`，mcp_client.py 行 49-54），断连后后台重连，重连期间 `_call_http_tool` / `_call_stdio_tool` 短路返回「服务暂时不可用」文本（行 851-852、882-883）。MCP5（mcp-oauth2，已设计）建立了**认证级**不可用标志 `_auth_unavailable`（行 151），正交于连接健康，命中时 `_call_http_tool` 返回「认证不可用」文本（行 875-879）。

但 docs/capabilities/mcp.md 列为 v1.0 规划项（`[ ]`）的「**完整降级策略**」尚未实现，当前状态存在三个缺口：

- **降级行为对 AI 不透明（schema 不摘除）**：服务降级/不可用时，其工具仍留在 `tool_registry.get_schemas()` 返回的 schema 列表里（tool_registry.py 行 90-92 扁平返回全部）。AI 仍会看到并尝试调用这些工具，只是在调用时拿到一段「不可用」文本——浪费一次 tool-use 轮次、污染上下文。docs 场景 5 要求「工具从 AI 可见列表中**临时移除**」，当前未做到。
- **无可配置降级模式**：docs 定义了三种模式——`degrade`（默认，临时移除该服务工具，其余正常）、`strict`（服务不可用时停止整个 agent）、`silent`（仅记录日志，不外部通知）。当前只有硬编码的「返回不可用文本」一种行为，模式不可配置。
- **两种正交不可用态行为不统一**：连接级（MCP3 `_health`）与认证级（MCP5 `_auth_unavailable`）各自在 `_call_*_tool` 里独立短路、各自返回不同文本，且都只作用于「调用时」，没有一个统一的「该服务此刻工具是否可用」判定供 schema 过滤与降级模式消费。

这是 MCP4（完整降级策略），**建立在 MCP3 连接健康与 MCP5 认证不可用之上**。本 change 不重新定义这两个正交态，而是在其上提供**统一的可用性判定 + schema 摘除 + 可配置降级模式 + 恢复后重新可用**，把 docs 场景 5 接通。本 change 聚焦降级策略本身，不碰 MCP3 的重连机制与 MCP5 的 token 生命周期。

## What Changes

- **统一可用性判定**：引入一个「服务工具此刻是否对 AI 可用」的单点判定，**整合** MCP3 连接健康（`_health is HealthState.healthy`）与 MCP5 认证不可用（`_auth_unavailable`）两个正交态：任一态判定不可用，则该服务工具整体视为不可用。该判定按 server 实例读取，不引入新的全局可变状态。
- **schema 摘除与恢复**：服务不可用时，其工具从 AI 可见的 schema 列表中**临时摘除**（不再出现在喂给 LLM 的 tools 里）；服务恢复（MCP3 重连成功 / MCP5 认证清除）后，其工具自动重新出现在 schema 列表中。摘除是「过滤视图」，不删除 `tool_registry` 注册项（恢复才能无副作用重新可见）。
- **可配置降级模式**：引入 per-server（缺省全局）降级模式 `degrade` / `strict` / `silent`：
  - `degrade`（默认）：摘除该服务工具，其余服务与对话正常进行。
  - `strict`：该服务不可用时，当前 agent 运行以明确错误终止（不静默继续）。
  - `silent`：与 `degrade` 同样摘除工具，但仅记录日志、不产生面向用户/外部的降级通知。
- **register_all 启动降级与运行时降级统一**：`register_all`（行 461-466）已实现「单服务启动连接失败 → log warning、不阻断平台启动」。本 change 明确：启动失败的服务等同进入「不可用」态，受同一套降级模式与 schema 摘除约束——`degrade`/`silent` 下其工具不出现在 schema、平台正常启动；`strict` 语义在 design 钉死（启动期 strict 的影响范围）。
- **降级期调用保持安全**：即便某工具因竞态仍被调用（schema 摘除与一次调用之间的时间窗），调用路径 MUST 仍返回明确的不可用结果（沿用 MCP3/MCP5 既有短路），绝不进入真实网络/子进程，绝不裸抛或卡住。

## Capabilities

### New Capabilities
- `mcp-degradation`: MCP 服务完整降级策略——统一整合 MCP3 连接健康与 MCP5 认证不可用两正交态为单点「工具可用性」判定；不可用服务的工具从 AI 可见 schema 临时摘除、恢复后自动重新可见；可配置降级模式 `degrade`（默认，摘除工具其余正常）/ `strict`（不可用即终止 agent）/ `silent`（摘除但仅记录日志）；register_all 启动失败降级与运行时降级统一受约；降级期调用仍安全返回不可用结果，不进真实请求、不裸抛、不卡住。状态按 server 实例读取，不引入全局可变状态。

### Modified Capabilities
<!-- 不修改既有 spec 的需求级行为。MCP3（mcp-health-reconnect）的「降级期间工具调用返回不可用信号」与 MCP5（mcp-oauth2-auth）的「认证不可用直接返回结果」是调用时短路；本 change 在其上新增 schema 摘除与降级模式，是其上层的新增能力，以 New Capabilities 承载，不改 MCP3/MCP5 既有可观察行为。 -->

## Impact

- **代码**：
  - 修改 `src/fleetent/mcp_client.py`：新增统一可用性判定（读 `_health` + `_auth_unavailable`，按 server 实例）；新增 server 工具名 → server 映射查询（用于 schema 过滤），不引入全局可变状态。
  - 修改 `src/fleetent/tool_registry.py`：`get_schemas()` 在返回前过滤掉「来自不可用 MCP server」的工具 schema（过滤视图，不删注册项），过滤判定由 mcp_client 提供（tool_registry 不反向依赖 mcp_client 的内部状态——经由可注入的过滤钩子，避免分层倒置，见 design D4）。
  - `McpServerConfig` 增加 `degrade_mode` 字段（`degrade` / `strict` / `silent`，默认 `degrade`），与既有 `auth_type` 风格一致；`strict` 模式的终止信号在 agent_loop 可消费的形式由 design 钉死。
- **配置**：`config/mcp.yaml` per-server 增加可选 `degrade_mode`（缺省 `degrade`，零配置可用）；可选全局默认。
- **测试**：扩展 `tests/test_mcp_client.py` 与 `tests/test_tool_registry.py`：覆盖统一可用性判定（连接降级、认证不可用、二者任一即不可用、二者均健康则可用）；schema 摘除与恢复；三种降级模式行为；register_all 启动失败降级；降级期调用仍安全返回。外部 HTTP 用 `respx` mock、stdio 子进程用 `unittest.mock` mock，**不发真实请求、不起真实子进程**；状态隔离用 tmp_path / monkeypatch。
- **不影响**：MCP3 的探活/重连机制本身、MCP5 的 token 获取/刷新与 `_auth_unavailable` 置位逻辑、命名空间格式、健康服务的正常注册与调用、非 MCP 工具的 schema。

## Dependencies

- **`src/fleetent/mcp_client.py`（已实现）**：本 change 在其 `HealthState` / `get_health` / `_auth_unavailable` 之上读取状态，复用 `_unavailable_result` 与既有调用短路；新增统一判定与 server 映射查询。
- **MCP3（`openspec/changes/mcp-health-reconnect/`）**：提供连接级健康态契约（`healthy` / `degraded` / `unavailable`、按 server 隔离、恢复后自动重连）。本 change 的「连接级不可用」直接消费该契约。
- **MCP5（`openspec/changes/mcp-oauth2/`）**：提供认证不可用态契约（`_auth_unavailable` 正交于连接健康、由配置重载/重新注册清除）。本 change 的「认证级不可用」直接消费该契约。
