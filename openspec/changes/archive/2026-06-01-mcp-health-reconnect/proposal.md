## Why

MCP1（mcp-http-streamable，已合入）让标准 HTTP MCP 服务能接进来，MCP2（mcp-session-management）处理会话级过期重建。但**连接级断连**仍无人维护：

- **启动后无健康监测**：`register_all` 只在启动时连一次，连上后就不管了。运行中服务挂掉（HTTP 不可达、stdio 子进程死亡）平台毫不知情——直到 agent 调用该服务工具时 `_call_http_tool` / `_call_stdio_tool` 抛异常，错误才暴露，且每次调用都重新撞墙。docs/capabilities/mcp.md 把「健康检查与重连」「断开后自动恢复（场景 3）」列为 v1.0 规划项（`[ ]`）。
- **断连异常未归一化**：连接断开抛出的异常（httpx 连接错误、子进程 EOF）没有被归类。AR5（error-classification，已合入）**已预留** `mcp_disconnect` 分类码（`should_retry=True`，含义「尝试重连，失败则降级」），但当前没有任何代码路径产生该分类、消费该标志位——预留码处于「定义齐全但无人接通」状态。
- **断连后无重连、无降级反馈**：服务断开后既不会后台重连，工具调用也只是裸抛异常，而非返回「服务暂时不可用」的明确信号；重连成功后也无自动恢复。

这是 MCP3（健康检查与重连），同时依赖 **MCP1**（连接/传输地基）**和 AR5**（错误分类）。本 change 的核心是**把 AR5 已预留的 `mcp_disconnect` 路径接通**：mcp_client 侧把断连异常判定为 `ErrorCategory.mcp_disconnect`、直接读 `CLASSIFICATION_TABLE` 取该分类的 `should_retry=True`（**不经 `classify()`**——`classify()` 不识别断连异常，详见 design D1）→ 尝试重连 → 失败则降级（标记服务不可用、工具返回「服务暂时不可用」）→ 后台按指数退避重连，恢复后自动重新启用。本 change 聚焦**连接级健康与重连**，不碰会话级过期（MCP2）与认证（MCP5）。

## What Changes

- **接通 AR5 `mcp_disconnect` 路径**：工具调用（`_call_http_tool` / `_call_stdio_tool`）捕获连接级断连异常后，由 mcp_client 侧把它判定为 `ErrorCategory.mcp_disconnect`、直接读 `error_classifier.CLASSIFICATION_TABLE[mcp_disconnect]` 取 `should_retry=True` 标志位决定「尝试重连」（**不经 `classify()`**——经核实 `classify()` 仅识别 `APIStatusError`，断连异常喂进去只会得到 `unknown`，见 design D1）。本 change 是 AR5 design D3 中「`mcp_disconnect` 重连动作由 mcp_client 侧后续实现」所指的那个后续实现。
- **健康状态跟踪**：为每个已注册服务维护连接健康状态（如 `healthy` / `degraded` / `unavailable`），按 server 实例隔离持有（不进模块级可变全局），可注入/重置以便测试。
- **周期性探活**：后台定期探活——HTTP 服务发轻量请求（如再次 `tools/list` 或 ping），stdio 服务检查子进程存活；探活失败累计触发降级与重连。
- **指数退避重连**：断连后按指数退避重连（1s → 2s → 4s → … 最长 60s）；连续失败达阈值后标记**永久不可用**（`unavailable`），停止自动重连，需手动触发重连。重连成功后状态恢复 `healthy`，工具自动重新可用。
- **降级反馈**：服务处于 `degraded` / `unavailable` 时，对其工具的调用 MUST 返回明确的「服务暂时不可用」结果，而非裸抛异常或静默卡住；其他服务工具不受影响。
- **复用既有地基**：探活/重连复用 MCP1 的 `initialize` / `tools/list` 与 stdio 会话；分类复用 AR5 `classify()`；调度可复用平台既有的 asyncio 后台任务/调度能力。

## Capabilities

### New Capabilities
- `mcp-health-reconnect`: MCP 服务连接级健康检查与重连——周期探活（HTTP ping / stdio 子进程存活）；断连异常由 mcp_client 侧判定为 AR5 `mcp_disconnect` 并直接读 `CLASSIFICATION_TABLE` 的 `should_retry` 标志位触发重连（不经 `classify()`）；指数退避重连（1s→2s→4s→…→60s）；连续失败达阈值标记永久不可用、需手动重连；降级期间工具调用返回「服务暂时不可用」；恢复后自动重新启用。健康状态按 server 隔离持有，不进全局可变状态。

### Modified Capabilities
<!-- 不修改既有 spec 的需求级行为。本 change 消费 AR5（agent-error-classification）已预留的 mcp_disconnect 分类码——AR5 spec 的「预留分类码不被主动返回」要求仅约束主循环可达的 LLM 异常，本 change 在 mcp_client 侧对断连异常产出该分类码，不与之冲突。AR5 行为不变，故以 New Capabilities 承载，非需求级 MODIFIED。 -->

## Impact

- **代码**：
  - 修改 `src/fleetent/mcp_client.py`：
    - 为每个服务维护连接健康状态（`healthy` / `degraded` / `unavailable`），按 server 实例持有（不进全局可变状态）。
    - `_call_http_tool` / `_call_stdio_tool` 捕获断连异常 → mcp_client 侧判定为 `ErrorCategory.mcp_disconnect`、直接读 `CLASSIFICATION_TABLE[mcp_disconnect]`（不经 `classify()`）→ 若 `should_retry`，转入重连/降级路径；降级期返回「服务暂时不可用」。
    - 新增周期探活与指数退避重连逻辑（可注入间隔/退避上限/失败阈值以便测试用短值）；新增手动触发重连入口。
  - 依赖 `src/fleetent/error_classifier.py`（AR5 已合入）：经核实 `classify()`/`_categorize()` 只识别 `APIStatusError`、对断连异常返回 `unknown`，**不会**返回 `mcp_disconnect`。本 change 在 mcp_client 侧把断连异常判定为 `ErrorCategory.mcp_disconnect`、直接读 `CLASSIFICATION_TABLE[mcp_disconnect]` 取标志位（不经 `classify()`、不改 AR5 分类表标志位）。
  - 探活后台任务的启动/关停接入 `server.py` lifespan（与现有 `mcp_client.register_all` / `close()` 同处）。
- **配置**：探活间隔、退避上限、永久不可用阈值作为**可注入参数**（默认值内置）；如需部署级可调，在 `config/mcp.yaml` per-server 或全局加可选字段（默认值保证零配置可用），在 Impact 与 design 说明。无云托管依赖。
- **测试**：扩展 `tests/test_mcp_client.py`，新增健康/重连用例（断连→classify→`mcp_disconnect`→重连成功恢复、重连失败→降级→工具返回「服务暂时不可用」、退避序列、达阈值标记永久不可用、手动重连恢复、探活检测断连）。外部 HTTP 用 `respx` mock，stdio 子进程用 `unittest.mock` mock，**不发真实请求、不起真实子进程**；用短退避/短间隔参数，不真实 sleep 长时间。
- **不影响**：MCP1 在服务健康时的正常注册/调用、MCP2 会话过期重建、命名空间格式、API Key 认证、AR5 分类表标志位、其他健康服务。
- **依赖与新依赖**：依赖 AR5（`error_classifier`，已合入）；探活/重连用 MCP 域内裸 `asyncio` 后台任务（`asyncio.create_task`，绑 server lifespan），**不挂 `cron_scheduler`/APScheduler**（与暂缓的定时任务功能解耦），不引入任何新依赖。
