## Why

Agent runtime、TUI、sandbox、agent lifecycle 各模块当前日志分裂为三套互不兼容的实现（structlog、stdlib logging、无日志），导致 agent 运行时关键事件不落盘、无脱敏、无统一 component 标记，线上排查几乎无法依赖日志。项目已有成熟的自定义结构化日志（`structured_logging.py`），支持文件落盘、自动脱敏、分级过滤，应全面采用。

## What Changes

- 将 `runtime/`、`tui/`、`integrations/sandbox/`、`platform/agent_lifecycle/`、`im_gateway/slack_supervisor.py` 的所有日志调用迁移到 `get_logger("component")` API
- 删除对 `structlog` 和 `logging`（stdlib）的直接依赖（上述模块范围内）
- 为当前零日志的文件新增结构化日志覆盖：`snapshot.py`、`budget.py`、`loop_detector.py`、`tool_guardrails.py`、`message_hygiene.py`、`error_classifier.py`、`agent_lifecycle/controller.py`、`agent_lifecycle/materialize.py`、`agent_lifecycle/lifecycle_admin_api.py`
- 统一 component 命名规范：点号分层（如 `runtime.loop`、`sandbox.client`）
- 采用三级事件策略：`info` 记关键节点，`debug` 记中间状态，`trace` 记原始数据

## Capabilities

### New Capabilities

- `agent-runtime-logging`：agent runtime 模块（loop、context、sub_agent、snapshot、budget、loop_detector、guardrails、hygiene、error、agent_app）的结构化日志覆盖规范
- `agent-tui-logging`：TUI 模块（app、backend、dispatch、transport）的结构化日志覆盖规范
- `agent-sandbox-logging`：sandbox 模块（client、config、cleanup、enablement）的结构化日志覆盖规范
- `agent-lifecycle-logging`：agent lifecycle 平台控制面（controller、materialize、api）的结构化日志覆盖规范

### Modified Capabilities

（无 spec 级行为变更，仅实现层替换）

## Impact

- **修改文件**：20 个源文件（见 What Changes）
- **依赖变更**：上述模块移除 `structlog`、`logging` 导入，改用 `fleetent.observability.structured_logging`
- **无 API 变更**：对外接口不变，日志为内部可观测性
- **测试**：现有测试无需改动（日志调用不影响行为断言）；新增测试验证关键事件在 `_logger` 上被调用
