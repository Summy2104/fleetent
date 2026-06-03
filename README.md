# fleetent

fleetent 是一个面向企业内网部署的轻量 Agent 平台。项目基于 Python 和 FastAPI 构建，不依赖 LangChain / LlamaIndex / LangGraph 等 AI 框架，核心目标是在客户自己的部署边界内运行 Agent、工具、记忆、知识库和治理能力。

核心能力：

- 多用户 HTTP、Slack、Telegram 和终端 TUI 入口；
- OpenAI-compatible 模型路由、fallback 和 provider 配置；
- 工具调用、MCP 工具服务、子 Agent 和沙箱执行；
- User Memory、Shared Memory、长期上下文和知识库检索；
- medium / high 风险工具调用的人类审批门控；
- trace、usage、performance、diagnostics 和 Pilot 验证报告；
- SQLite-first 本地运行时，schema 生命周期由 Alembic 管理。

## 快速开始

```bash
# 前置条件：Python 3.12+、uv，以及一个 LLM provider API key。
git clone <repo-url>
cd fleetent
uv sync
cp config/settings.yaml.example config/settings.yaml
export ANTHROPIC_API_KEY=sk-ant-...
```

运行一次 CLI 请求：

```bash
uv run fleetent "What time is it, and what is 123 * 456?"
```

启动 HTTP 服务：

```bash
uv run uvicorn fleetent.server:app --reload --port 8765
```

创建用户并调用 `/chat`：

```bash
uv run fleetent-admin create-user --name "Alice"
# api_key: ma-<64 hex chars>

curl -s http://localhost:8765/chat \
  -H "Authorization: Bearer ma-<64hex>" \
  -H "Content-Type: application/json" \
  -d '{"message": "What is 7 * 8?"}' | grep "^data:"
```

运行交互式终端 TUI：

```bash
uv run fleetent-tui --url ws://127.0.0.1:8765/ws --token ma-<64hex>
```

## 架构

```text
HTTP / IM / TUI
      |
      v
NormalizedMessage / WebSocket request
      |
      v
agent_loop.run() / run_stream()
      |
      +--> long-term context, memory, knowledge base
      +--> model_router
      +--> tool_registry
              |
              +--> built-in tools
              +--> MCP tools
              +--> sub-agents
              +--> sandbox tools
      |
      v
observability traces, usage, diagnostics, session persistence
```

代码库正在从 legacy 平铺模块逐步迁移到模块化单体。新增代码优先放在 `src/fleetent/` 下对应 package，并通过 public API 跨模块调用。

| Package | 职责 |
| --- | --- |
| `runtime` / flat runtime modules | Agent loop、终止、取消、预算、session runtime 等运行时行为。 |
| `governance` | 审批门、配额、审计、blocklist 和 agent policy。 |
| `platform` | Admin API、用户管理、Agent 管理、connector 管理和控制台入口。 |
| `im_gateway` | Slack / Telegram 消息归一化与路由。 |
| `integrations` | MCP、sandbox 和外部集成边界。 |
| `intelligence` | Memory、Shared Memory、long-term context、reflection、vector store 和 knowledge base。 |
| `observability` | Trace、usage / performance summary、diagnostics 和 verification report。 |
| `tui` | 交互式终端客户端和 WebSocket dispatch 协议。 |

已迁移 package 的 internal 实现不应被其他 package 直接 import；跨模块调用应走 public API、CLI、HTTP 或明确的管理入口。

## 配置

配置从环境变量和 `config/settings.yaml` 读取。

常规 LLM 路径需要：

| 变量 | 说明 |
| --- | --- |
| `ANTHROPIC_API_KEY` | 默认 Anthropic-compatible route 凭据。 |

常见可选变量：

| 变量 | 说明 |
| --- | --- |
| `SLACK_BOT_TOKEN` | 启用 Slack adapter。 |
| `SLACK_APP_TOKEN` | Slack Socket Mode 需要与 `SLACK_BOT_TOKEN` 一起配置。 |
| `TELEGRAM_BOT_TOKEN` | 启用 Telegram adapter。 |
| `MICROSANDBOX_URL` | Sandbox 服务地址。 |
| `FLEETENT_SKILLS_DIR` | 覆盖默认 skills 目录。 |

模型路由通过 `settings.yaml` 和 `model_router.py` 配置，使用 OpenAI-compatible endpoint。不要提交真实 API key、IM token、OAuth 凭据或本地 `.env` 文件。

## HTTP API

### 认证

`/chat` 需要 admin CLI 签发的 Bearer token：

```text
Authorization: Bearer ma-<64hex>
```

### POST /chat

返回 Server-Sent Events：

```bash
curl -s http://localhost:8765/chat \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the current time?"}'
```

事件示例：

```text
data: {"type": "text_delta", "content": "The current"}
data: {"type": "tool_call", "name": "get_current_time", "args": {}}
data: {"type": "tool_result", "name": "get_current_time", "content": "..."}
data: {"type": "done", "content": "The current time is ..."}
```

### GET /health

```json
{"status": "ok", "adapters": {"slack": false, "telegram": false}}
```

## 工具与 MCP

内置工具通过 `@tool` 注册：

```python
from fleetent.tool_registry import tool


@tool
def search_database(query: str, limit: int = 10) -> str:
    """Search the internal database. Returns matching records as JSON."""
    ...
```

MCP-compatible 工具服务可以写入 `config/mcp.servers.yaml`：

```yaml
servers:
  - id: internal_tools
    url: http://localhost:3000
    auth_type: api_key
    api_key_env: INTERNAL_TOOLS_API_KEY
```

MCP 工具会注册为 `{server_id}__{tool_name}`，避免与内置工具重名。

## Skills

Skill 文件放在 `skills/<skill-name>/SKILL.md`。服务启动时会扫描 skill，Agent 可按需读取匹配的 skill 指令。

```text
skills/
  summarize-doc/
    SKILL.md
```

## 开发

安装依赖：

```bash
uv sync
```

运行测试：

```bash
uv run pytest
uv run pytest -x -q
uv run pytest tests/unit
uv run pytest tests/integration
uv run pytest tests/e2e
uv run pytest tests/evaluation
```

运行质量检查：

```bash
uv run ruff format src tests
uv run ruff check src tests
uv run mypy src
PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py
```

生成 Pilot 验证报告：

```bash
uv run python scripts/generate_pilot_verification_report.py
```

## 文档

主要文档：

| 文档 | 说明 |
| --- | --- |
| `docs/architecture.md` | 架构总览和 capability 索引。 |
| `docs/capabilities/` | 能力域设计、状态和验收文档。 |
| `docs/capabilities/roadmaps/` | Pilot readiness、Runtime / Tooling、Intelligence、Observability / Deployment、Platform / Channel roadmap。 |
| `docs/deployment/` | Pilot 安装、运行、验收和 secret 处理。 |
| `docs/records/` | 集成记录、执行日志和 review / apply 决策记录。 |
| `openspec/` | Spec-driven proposals、tasks 和归档 changes。 |

## License

Apache 2.0。详见项目 license metadata。
