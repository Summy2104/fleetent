## Context

`AgentFile`（`agent_config.py`）中有 6 个字段自上次架构演进后已从未被任何运行时代码读取：
- `microsandbox_url`：sandbox 始终走 Docker CLI，microsandbox 集成从未落地
- `image_gen_url / image_gen_model`：image_gen_client 已改为从 `models.routes["image_generation"]` 解析，旧字段被绕过
- `vision_url / vision_model`：vision_client 已改为从 `models.routes["vision"]` 解析，旧字段被绕过
- `log_format`（AgentFile 级别）：`configure_logging()` 只接受 `Settings`，从未从 `AgentFile.log_format` 读取

`agent.yaml.example` 也缺少 Telegram connector 示例和 MCP 超时字段示例，`line 1` 的 `#` 注释丢失。

## Goals / Non-Goals

**Goals:**
- 从 `AgentFile` 删除 5 个死字段，消除 schema 与实现的误导性不一致
- 接入 `log_format`：`fleetent agent run` 在 `boot()` 阶段从 agent.yaml 配置日志系统
- 补全 `agent.yaml.example`：Telegram 示例、MCP 超时字段、修复 typo
- 补全 `.env.example`：BILLING_DB_DSN + Telegram token

**Non-Goals:**
- 实现 microsandbox 集成（字段删除，不做替代实现）
- 为 platform 模式（多 agent）配置日志（platform 继续从 `Settings` 读取）
- 修改 image/vision 的路由逻辑（已通过 model routes 正常工作）

## Decisions

**D1：`configure_structured_logging` 接口不改，`agent_app.boot()` 直接读取 agent 字段调用**

`config.py:configure_logging(settings: Settings)` 的签名不变，避免引入泛型参数扰乱现有 platform 调用链。在 `agent_app.boot()` 中单独提取 agent 的日志字段，直接调用底层 `configure_structured_logging(console_level, file_level, directory)` 和 format 判断。

理由：`Settings` 和 `AgentFile` 虽然有相同字段，但用 Union/Protocol 会让 `config.py` 对 `AgentFile` 产生依赖，违反依赖方向（`config` 是基础层，不应依赖 `agent_config`）。

**D2：`log_format` 仅在 standalone agent 启动时生效**

`boot()` 读取 `agent.log_format` 和 `agent.observability.logging.*` 配置日志。platform server（`server.py`）继续用 `Settings.log_format`，两者互不干扰。

**D3：5 个死字段直接删除，不保留 shim**

这些字段从未在生产代码中被读取，schema 中存在反而会误导运维。删除后 `agent.yaml` 使用旧字段会触发 Pydantic `extra="forbid"` 错误，提前暴露配置问题。

**D4：`agent.yaml.example` 中 `observability.logging` 保留**

`observability.logging.directory` 等字段确实被 `diagnostics.py` 读取用于确定 log 目录，不是死字段，继续在 example 中展示。

## Risks / Trade-offs

- **Breaking**：已有 `agent.yaml` 包含被删除字段的部署会在启动时因 `extra="forbid"` 失败。缓解：在 PR 描述和 commit 中明确列出需要从 `agent.yaml` 删除的字段名。
- **日志覆盖顺序**：`boot()` 中调用日志配置发生在 `load_dotenv` 之后、`scan_home` 之后，确保 `.env` 已加载（因为 `observability.logging.directory` 可能引用 env var 解析后的路径）。
