# fleetent 总体架构

## 定位

面向企业 on-premises 部署的 Lean Agent 平台。核心主张：

- **部署主权**：跑在客户自己的服务器上，数据不出内网
- **可治理**：每次 agent 运行的 trace、成本、审批全部可查
- **可适配**：Skill 系统让领域专家无需改代码即可定制 agent 行为

技术哲学：最少依赖，直接调 SDK，不引入 AI 框架。

---

## 模块全景

```
src/fleetent/
  ┌─── 接入层 ──────────────────────────────────────────┐
  │  server.py          FastAPI：POST /chat (SSE)、Bearer 认证   │
  │  im_gateway/        Slack / Telegram / WhatsApp 适配器       │
  │    normalizer.py    NormalizedMessage 统一路由 pipeline       │
  │    slack.py         slack-bolt Socket Mode                    │
  │    telegram.py      python-telegram-bot polling               │
  └────────────────────────────────────────────────────┘
  ┌─── 编排层 ──────────────────────────────────────────┐
  │  agent_loop.py      while tool-use 核心循环                   │
  │  sub_agent.py       asyncio.gather 并行子 agent               │
  └────────────────────────────────────────────────────┘
  ┌─── 能力层 ──────────────────────────────────────────┐
  │  model_router.py    LLM 路由 + fallback 链                    │
  │  tool_registry.py   @tool 注册、dispatch、访问控制            │
  │  tools.py           内置工具（import 即注册）                 │
  │  skill_registry.py  关键词匹配，注入 system prompt            │
  │  context_mgr.py     in-session token 压缩                     │
  │  memory_layer.py    跨 session 事实提取与注入                 │
  │  mcp_client.py      MCP HTTP/stdio 工具注册                   │
  │  sandbox_client.py  Docker 隔离代码执行                       │
  │  permission_gate.py asyncio.Event 人工审批门                  │
  │  cron_scheduler.py  APScheduler 定时任务                      │
  │  webhook_router.py  Webhook 签名验证与消息提取                │
  └────────────────────────────────────────────────────┘
  ┌─── 基础层 ──────────────────────────────────────────┐
  │  user_store.py      用户/API key 管理（SQLite）               │
  │  agent_store.py     agent 定义 + channel 绑定（SQLite）       │
  │  im_user_store.py   IM 平台用户映射 + allowlist               │
  │  session_mgr.py     JSON session 持久化 + asyncio.Lock        │
  │  schedule_store.py  定时任务持久化（SQLite）                  │
  │  eval_logger.py     append-only JSONL trace 日志              │
  │  agent_policy.py    fnmatch 工具访问检查                      │
  │  config.py          pydantic-settings 配置体系                │
  │  admin.py           CLI 管理工具                              │
  └────────────────────────────────────────────────────┘
```

依赖方向单向向下：接入层 → 编排层 → 能力层 → 基础层。

---

## 端到端数据流

### HTTP 路径

```
POST /chat + Bearer token
  → server.py 认证（API key → user_id）
  → agent_loop.run_stream()
      ├─ 注入跨 session 记忆
      ├─ 匹配 Skill，注入 system prompt
      ├─ while True:
      │   ├─ context_mgr 检查是否需要压缩
      │   ├─ LLM streaming call（含 fallback 链）
      │   ├─ 流式输出 SSE text_delta
      │   └─ tool_calls → permission_gate → dispatch → loop back
      ├─ eval_logger 写 trace
      └─ memory_layer 异步提取事实（不阻塞响应）
  → SSE {"type": "done"}
```

### IM 路径

```
IM 消息
  → 平台适配器（Slack/Telegram）
  → im_user_store.get_or_create()     # 身份映射
  → normalizer.route()
      ├─ approve/reject 命令 → permission_gate.resolve()
      └─ 普通消息
          ├─ im_user_store 检查 allowlist
          ├─ agent_store 解析 agent（channel → user → default → 裸跑）
          └─ agent_loop.run() → 回写平台

### Webhook 路径

POST /webhook/{source_id}
  → webhook_router.verify_signature()  # HMAC-SHA256 或无 secret 直通
  → webhook_router.extract_message()   # 模板提取或 JSON 序列化
  → normalizer.route()                 # 复用 IM pipeline
```

### Cron 路径

```
APScheduler trigger
  → schedule_store 读取任务定义
  → agent_loop.run()
  → 结果通过 reply_func 回写（IM 消息或日志）
```

---

## 关键设计决策

| 决策 | 结论 | 理由 |
|------|------|------|
| 部署结构 | 模块化单体，单进程 | on-premises 天敌是复杂度，微服务带来不必要的运维负担 |
| LLM 调用 | 直接调 SDK，不用框架 | LangChain 等框架频繁 breaking change，debug 困难，与 Hermes/OpenClaw 问题性质相同 |
| 数据库 | SQLite（可升 PostgreSQL）| 零运维，on-premises 友好；模块内直接用 aiosqlite，不引入 ORM |
| Session 存储 | JSON 文件 + asyncio.Lock | 可调试，原子写（.tmp → rename）防损坏 |
| 工具审批 | asyncio.Event 门控 | 无轮询，优雅等待；重启后孤儿请求通过 cleanup_stale_approvals() 清理 |
| 代码执行隔离 | Docker CLI 封装 | 真隔离 + 资源限制；启动约 1s，可接受 |
| MCP 工具命名 | `{server}__{tool}` 双下划线 | 避免与内置工具名冲突，来源可追溯 |
| 记忆提取 | Haiku 异步提取，不阻塞响应 | 廉价且快；提取结果写 JSONL，top-20 条注入下次请求 |

---

## 能力域文档索引

详细设计和验收标准见各能力域文档：

| 文档 | 覆盖范围 |
|------|---------|
| [agent-runtime.md](capabilities/agent-runtime.md) | 核心循环、工具、Skill、MCP、沙箱、上下文压缩 |
| [im-gateway.md](capabilities/im-gateway.md) | Slack / Telegram / WhatsApp 接入、用户映射 |
| [memory.md](capabilities/memory.md) | 跨 session 记忆、自进化机制 |
| [scheduling.md](capabilities/scheduling.md) | Cron 定时任务、Webhook 事件触发 |
| [governance.md](capabilities/governance.md) | 权限审批、工具白名单、agent 定义与分配 |
| [platform.md](capabilities/platform.md) | 用户管理、API 认证、admin CLI |
| [observability.md](capabilities/observability.md) | 评估日志、数据统计、链路追踪 |
| [deployment.md](capabilities/deployment.md) | on-premises 打包、配置管理 |
