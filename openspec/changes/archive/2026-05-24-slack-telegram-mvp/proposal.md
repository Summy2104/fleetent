## Why

fleetent 已完成技术验证（agent loop、streaming、memory、48 个测试），但仍是单用户 CLI/HTTP 工具。需要扩展为可在企业内网运行的 Slack/Telegram IM 原生服务，验证"可治理、可部署"核心差异化，为后续 on-premises 商业化打基础。

## What Changes

- 新增 Slack + Telegram adapter，归一化消息格式后路由至 agent_loop
- 新增 session persistence，跨消息保持对话历史（DM session / thread session 两种模型）
- 新增 sub-agent，基于 asyncio.gather 并行执行，子 agent 使用全新上下文，最多两层嵌套
- 新增 permission gate，工具调用前双层检查：访问控制（agent.allowed_tools）+ 人工审批门（medium/high 两级）
- 新增 sandbox client，对接 microsandbox-server（MicroVM），工具执行在隔离环境中进行
- 新增 mcp_client，启动时注册外部 MCP server 工具至 tool_registry，命名规范 `{server_id}__{tool_name}`
- 新增 im_user 映射，将平台用户 ID 映射到内部 user_id
- 新增 agent 定义表（SQLite），存储 system_prompt 和 allowed_tools，支持后续管理后台
- 新增 alembic migration，管理 SQLite schema 版本
- 新增 pydantic-settings 配置管理，支持 env var 覆盖
- 新增 structlog 结构化日志
- 新增 Docker 单容器打包，支持 on-premises 部署

## Capabilities

### New Capabilities

- `im-gateway`: Slack Socket Mode + Telegram Long Polling adapter，统一消息格式，thread-first 回复
- `session-persistence`: 按 session_id 加载/保存对话历史，JSON 文件存储，支持 context 压缩后覆写
- `sub-agent`: 进程内 asyncio 并行 sub-agent，全新上下文，parent 摘要传递背景，最多两层
- `permission-gate`: tool_registry.dispatch 层访问控制 + asyncio.Event 人工审批门（medium/high），超时可配置
- `sandbox-client`: HTTP client 对接 microsandbox-server，per-session workspace 生命周期管理
- `mcp-client`: 启动时连接 MCP server，发现并注册工具至 tool_registry，透明化工具来源
- `im-user-mapping`: im_users 表，platform_user_id → 内部 user_id，首次交互自动创建
- `agent-definition`: agents + user_agents 表，定义 allowed_tools 和 system_prompt，用户绑定 agent
- `db-migration`: alembic 管理所有新增表的 schema 版本

### Modified Capabilities

- `user-store`: 新增 im_users 表，与现有 users 表关联（非行为变更，仅 schema 扩展）

## Impact

- **新文件**：`im_gateway/slack.py`, `im_gateway/telegram.py`, `im_gateway/normalizer.py`, `session_mgr.py`, `sub_agent.py`, `permission_gate.py`, `sandbox_client.py`, `mcp_client.py`, `agent_policy.py`, `config.py`, `migrations/`
- **现有文件扩展**：`user_store.py`（新增 im_users 查询）, `tool_registry.py`（dispatch 层新增访问控制）, `eval_logger.py`（新增 IM 字段）
- **新依赖**：`slack-bolt`, `python-telegram-bot`, `microsandbox`, `pydantic-settings`, `structlog`, `alembic`, `mcp`
- **部署变化**：宿主机需安装 microsandbox-server（原生守护进程），fleetent 打包为 Docker 镜像，docker-compose 编排
- **配置新增**：`config/mcp.yaml`（MCP server 连接信息），`.env.production`（密钥，gitignored）
