## Why

`AgentFile` 中存在 6 个已声明但从未被运行时代码读取的"死字段"（`microsandbox_url`、`log_format`、`image_gen_url`、`image_gen_model`、`vision_url`、`vision_model`），同时 `agent.yaml.example` 缺失 Telegram connector 示例和 MCP 超时字段示例，`log_format` 虽然在 `agent-scoped-runtime-config` 规范中要求从 agent 配置读取，但实际运行时未接入。

## What Changes

- **删除死字段**：从 `AgentFile` schema 中移除 `microsandbox_url`、`image_gen_url`、`image_gen_model`、`vision_url`、`vision_model` 五个字段（sandbox 用 Docker 直接运行，image/vision 端点已统一走 `models.routes`）
- **接入 `log_format`**：`fleetent agent run` 启动时从 agent.yaml 读取 `log_format` 和 `observability.logging.*`，调用 `configure_structured_logging` 配置日志系统
- **补全 `agent.yaml.example`**：
  - 修复第 1 行 `#` 注释丢失的 typo
  - 删除已移除的 5 个死字段示例内容
  - 补充 `connectors.telegram` 完整示例块
  - 在 `mcp_servers` 示例中补充 `connect_timeout` / `call_timeout` 字段
- **补全 `.env.example`**：补充 `BILLING_DB_DSN` 和 Telegram bot token 示例

## Capabilities

### New Capabilities

- `agent-log-format-wiring`：standalone agent runtime 从 `agent.yaml` 读取 `log_format` 和 `observability.logging.*`，在 `agent_app.boot()` 阶段配置结构化日志，使日志格式和级别可按 agent 配置

### Modified Capabilities

- `agent-scoped-runtime-config`：移除对 `microsandbox_url`、`image_gen_url`、`image_gen_model`、`vision_url`、`vision_model` 的规范描述（spec 中的"image/vision endpoints"改为"通过 models.routes 配置"）；补充 `log_format` 运行时接入的 REQUIREMENT
- `mcp-per-server-timeout`：补充 "Timeouts SHALL appear in the official agent.yaml example" 要求，确保运维人员可发现此配置
- `per-agent-telegram-connector`：补充 "The official agent.yaml.example SHALL include a telegram connector example block" 要求

## Impact

- `src/fleetent/agent_config.py`：删除 5 个字段定义
- `src/fleetent/config.py`：提取 `configure_logging` 为接受 duck-typed 接口的函数，使 `AgentFile` 和 `Settings` 均可调用
- `src/fleetent/runtime/agent_app.py`：`boot()` 中在加载 agent 后调用日志配置
- `agents/default/agent.yaml.example`：更新示例文件
- `agents/default/.env.example`：更新示例文件
- 测试：`tests/unit/test_agent_config.py`、`tests/unit/test_agent_app_logging.py`（新增）
