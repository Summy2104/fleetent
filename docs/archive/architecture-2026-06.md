> **[历史记录]** 本文档为 2026-06 月中期架构草稿，已被 `docs/architecture/target-architecture.md` 定版取代。内容以当前架构文档为准。

# fleetent 平台架构（2026-06）

> 基于 main 分支当前代码（ab347ae → ff4e73e）生成，反映最新迁移状态。

---

## 定位

面向企业 on-premises 部署的 Lean Agent 平台。

- **部署主权**：运行在客户自有服务器，数据不出内网
- **可治理**：每次 agent 运行的 trace、成本、审批全部可查
- **可适配**：Skill 系统让领域专家无需改代码即可定制 agent 行为
- **技术哲学**：最少依赖，直接调 SDK，不引入 AI 框架

---

## 架构全景

```
┌──────────────────────────────────────────────────────────────────────┐
│                          接入层                                       │
│                                                                      │
│   HTTP /chat (SSE)   WebSocket /ws   IM Gateway   CLI (fleetent)     │
│   Webhook /webhook/{id}              TUI (fleetent-tui)              │
└──────────────┬──────────────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────────────┐
│                         IM 归一化层                                   │
│   im_gateway/normalizer.py — NormalizedMessage                      │
│   Slack (bolt Socket Mode, per-agent) │ Telegram (polling, per-owner)│
└──────────────┬──────────────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────────────┐
│                      Agent 解析层（零 DB）                            │
│   agent_config.py — 读 agent.yaml 文件索引                           │
│   channel → user → default 优先级                                    │
│   运行时完全文件驱动，DB/console 仅作为 authoring 来源                 │
└──────────────┬──────────────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────────────┐
│                     Runtime Loop（核心执行引擎）                      │
│   runtime/loop.py                                                    │
│                                                                      │
│   Session Load → Long-Term Ctx Inject → Model Call → Tool Dispatch  │
│        ↑                                                    │        │
│        └──────── Tool Results + Memory Extraction ──────────┘        │
│                                                                      │
│   运行治理子模块：                                                    │
│   termination · loop_detector · budget · layered budget             │
│   cancellation · message_hygiene · error_classifier                 │
│   tool_guardrails · sub_agent_lifecycle                             │
└──────┬────────────────────┬────────────────────┬───────────────────┘
       │                    │                    │
┌──────▼────────┐  ┌────────▼────────┐  ┌───────▼──────────────────┐
│  model/       │  │  tools/         │  │  intelligence/           │
│               │  │                 │  │                          │
│ resolver.py   │  │ registry.py     │  │ memory/                  │
│               │  │ schema_builder  │  │   extraction.py          │
│ 标准路由 key: │  │ builtin_tools   │  │   store.py               │
│  default      │  │ file_tools  NEW │  │ knowledge_base/          │
│  vision       │  │ shell_tool  NEW │  │   config.py              │
│  embedding    │  │ web_tools   NEW │  │   operations.py          │
│  rerank       │  │ interaction NEW │  │   bindings.py            │
│  image_gen    │  │ @tool+avail     │  │   runtime.py             │
│  memory_ext   │  │ schema/dispatch │  │ vector_store/            │
│  audio_*      │  │ MCP + plugins   │  │   runtime.py             │
│               │  │ vision_client   │  │   embeddings.py          │
│ 每 agent 独立 │  │ image_gen_client│  │   rerank.py              │
│ 路由策略      │  │ multimodal      │  │ long_term_ctx.py         │
│ fallback 链   │  │ result_trunc    │  │ reflection.py            │
│ provider 健康 │  │                 │  │                          │
└───────────────┘  └─────────────────┘  └──────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                    平台控制面（Control Plane）                        │
│   server.py — 独立 FastAPI app，不含 IM / loop / sandbox            │
│                                                                     │
│   agent_lifecycle     │ agent_mgmt_console   │ agent_statistics     │
│   user_management     │ model_provider_mgmt  │ skill_management     │
│   kb_management       │ im_gateway_mgmt      │ chat_management      │
│   connector_mgmt      │ resource_monitoring  │ askit_console        │
│   admin_cli                                                         │
│   权限：Bearer ma-<64hex>                                            │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                       存储层                                         │
│   SQLite data/users.db（Alembic 052 版本）                           │
│   Session JSON files（session/manager.py 原子写）                    │
│   Vector Store 后端（Qdrant 或 SQLite in-memory，可替换）             │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 核心数据流

### 一次聊天请求（IM 路径）

```
IM 消息（Slack / Telegram）
  → im_gateway 适配器（per-agent Slack bolt / per-owner Telegram polling）
  → im_user_store：(platform, platform_user_id) → 内部 User，首次自动创建
  → normalizer.route()：构造 NormalizedMessage
      │
      ├─ approve/reject 命令 → governance.permission_gate.resolve()
      │
      └─ 普通消息
            → allowlist 检查（allow_channels / allow_users 来自 agent.yaml）
            → agent_config.get_agent_for_context()：文件索引解析（零 DB）
            → session/manager.py：原子读 JSON transcript
            → intelligence/long_term_ctx.py：
                  注入用户记忆 + KB 检索 + team shared memory（token budget 控制）
            → tools/registry.get_schemas()：按 allowed_tools 过滤 schema
            → model/resolver.py：route_key=default → provider/endpoint
            → AsyncOpenAI 流式调用
            → Tool Dispatch Loop（runtime/loop.py）：
                  governance.permission_gate（medium/high 风险审批）
                  tool dispatch（file/edit/search · bash_exec · web_fetch/search ·
                                 clarify/todo · run_code · vision · image_gen · MCP）
                  loop_detector / termination / guardrails
            → intelligence/memory/extraction.py：异步提取语义记忆写回
            → session/manager.py：.json.tmp → rename 原子写
            → 回写 IM 平台
```

### HTTP / WebSocket 路径

```
HTTP POST /chat（SSE）
  → server.py Bearer 认证
  → run_stream()（runtime/loop.py）
  → SSE 流式输出

WebSocket /ws
  → tui/dispatch.py：send / abort / approve / session.*
  → run_stream() 事件驱动
  → fleetent-tui 客户端渲染（tui/render.py）

Webhook POST /webhook/{source_id}
  → server.py 查找运行时来源
  → HMAC-SHA256 签名验证
  → extract_message（模板提取 / JSON 序列化）
  → normalizer.route() → run()
```

---

## 模块地图（当前实现状态）

```
src/fleetent/
  server.py              ← 控制面 FastAPI（不含 IM/loop/sandbox）
                           lifespan: scan_skills + agent_config.scan + load_plugins
  runtime/               ← [已包化] 核心执行引擎
    loop.py              ←   while tool-use 核心循环；run() + run_stream()
    context.py           ←   in-session token 压缩；keep_tail identity check
    snapshot.py          ←   agent 快照 load_active；零 DB，文件驱动
    sub_agent.py         ←   asyncio.gather 并行子 agent（最大深度 1）
    termination.py       ←   终止原因分类（max_turns/tokens/failures/approval/guardrail）
    loop_detector.py     ←   arg 指纹 + repeat 阈值
    budget.py            ←   token 追踪
    layered-budget.py    ←   分层 budget 策略
    cancellation.py      ←   CancelToken 优雅关停
    message_hygiene.py   ←   消息净化与契约验证
    error_classifier.py  ←   错误分类（api_error/rate_limit/validation 等）
    tool_guardrails.py   ←   guardrail 策略评估与动作
    sub_agent_lifecycle.py ← 子 agent 进程管理
    agent_app.py         ←   独立 agent 进程入口（fleetent agent run）
    agent_init.py        ←   agent 运行时初始化
  model/                 ← [已包化] 模型路由与解析
    resolver.py          ←   agent-scoped 策略解析；STANDARD_ROUTE_KEYS；fallback 链
    __init__.py          ←   公共 API：get_resolver()
    provider_health.py   ←   ProviderHealthCache 熔断缓存
    [旧 model_router.py 已删除，resolver.py 为终态]
  tools/                 ← [已包化] 工具注册与调度
    registry.py          ←   @tool 装饰器（availability 门控）、dispatch、访问控制
    schema_builder.py    ←   类型注解→JSON Schema（list/Optional/Literal/Annotated）
    builtin_tools.py     ←   run_code（SB 门控）、schedule_task、sub_agent、invoke_agent
    file_tools.py        ←   read_file（分页/目录/二进制检测）、edit_file（6 层 fallback）、
                              search_content（grep）、search_files（glob）；ripgrep+py 回退
    shell_tool.py        ←   bash_exec：宿主机 Shell（risk=high），CancelToken+timeout
    web_tools.py         ←   web_fetch（HTML→Markdown）、web_search（SearXNG，availability 门控）
    interaction_tools.py ←   clarify（user_input_gate 挂起）、todo（session 便签）
    result_truncation.py ←   大输出截断 + 溢出文件（50KB；self_truncates 走 head+tail）
    plugin_loader.py     ←   动态插件发现与加载
    vision_client.py     ←   Claude vision API
    image_gen_client.py  ←   DALL-E 3 API
    multimodal.py        ←   图片附件组装
  skills/                ← [已包化] Skill 发现与匹配
    registry.py          ←   扫描 skills/ 目录、SKILL.md 关键词匹配、注入 system prompt
    audit.py             ←   静态注入审计
  session/               ← [已包化] 会话持久化
    manager.py           ←   JSON transcript；原子写；per-session asyncio.Lock
    index.py             ←   会话元数据索引；TTL/LRU 维护
  intelligence/
    memory/              ←   User Memory + Shared Memory：提取、维护、SQLite source of truth
      extraction.py      ←   LLM 提取语义记忆（identity/preferences/context）
      store.py           ←   memory_items 持久化；namespace 隔离
    knowledge_base/      ←   企业文档知识库
      config.py          ←   KB 配置模型（KnowledgeIndexingConfig / KnowledgeSourceConfig）
                              SourceType: google_drive | confluence
      operations.py      ←   连接器编排；Google Drive / Confluence 同步规划
      bindings.py        ←   agent ↔ KB 绑定
      runtime.py         ←   检索运行时；hybrid / graph / rerank / planner
    vector_store/        ←   向量索引基础设施
      runtime.py         ←   search / upsert / delete；namespace 隔离
      embeddings.py      ←   embedding provider 抽象
      rerank.py          ←   rerank provider 抽象（disabled / cohere / jina）
    long_term_ctx.py     ←   长期上下文调度；memory / KB / Shared Memory + token budget
    reflection.py        ←   反思报告；读取 traces/memory/KB 信号，只读，不自动写回
  integrations/
    mcp/                 ←   MCP HTTP/stdio client；工具注册为 {server}__{tool}
    sandbox/             ← [已包化] Docker CLI 封装；隔离 Python 执行
  governance/
    permission_gate.py   ←   asyncio.Event 人工审批门（medium/high 风险）
    user_input_gate.py   ←   asyncio.Event 用户输入门（clarify 工具用，独立于审批门）
    agent_policy.py      ←   fnmatch 工具访问检查（allowed_tools 白名单）
  platform/              ←   控制面管理 API（独立 FastAPI app）
    agent_lifecycle/     ←   agent 进程 start/stop；materialize home
    agent_management_console/ ← agent CRUD、版本、console UI
    agent_statistics/    ←   agent 使用统计
    user_management/     ←   用户/角色/API key/邀请
    model_provider_mgmt/ ←   provider 注册、路由、fallback 策略
    skill_management/    ←   skill 启用/禁用、per-agent 白名单
    kb_management/       ←   KB 数据源 CRUD、触发同步、connector 配置
    im_gateway_mgmt/     ←   IM 凭据配置、channel bindings
    chat_management/     ←   会话/transcript 查询
    connector_mgmt/      ←   用户级外部工具授权连接器
    resource_monitoring/ ←   资源使用监控
    askit_console/       ←   admin "Chat" playground（接入真实 agent loop）
    admin_cli/           ←   CLI：create-user / list-users / rotate-key 等
    config_validation.py ←   配置安全校验（inline secret 检测）
    maintenance.py       ←   维护任务
  im_gateway/
    normalizer.py        ←   NormalizedMessage；统一路由 pipeline；访问控制
    clarify_renderer.py  ←   clarify choices 渲染（Slack Block Kit / Telegram 键盘 / 文字）
    slack.py             ←   slack-bolt Socket Mode；per-agent 连接
    slack_supervisor.py  ←   一个 agent 一条 Socket Mode 连接；server 启动管理
    telegram.py          ←   python-telegram-bot；per-owner polling
  tui/                   ←   交互式终端（fleetent-tui，WebSocket 客户端）
    app.py               ←   AppController + prompt_toolkit 主循环
    dispatch.py          ←   send / abort / approve / session.*
    backend.py           ←   GatewayBackend（websockets 连接、收发、重连）
    render.py            ←   rich 渲染（流式文本/工具面板/审批提示/状态行）
    commands.py          ←   斜杠命令解析 + Completer
    protocol.py          ←   newline-delimited JSON-RPC 2.0 编解码
    transport.py         ←   Transport 抽象 + WSTransport
  agent_config.py        ←   文件驱动 agent 配置；build_index()；零 DB 运行时解析
  cron_scheduler.py      ←   APScheduler 定时任务；从 SQLite 动态恢复调度；
                              注册维护任务（每日 spillover 文件清理）
  webhook_router.py      ←   Webhook 签名验证（HMAC-SHA256）、消息提取
  user_store.py          ←   SQLite 用户/API key 管理
  agent_store.py         ←   SQLite agent 定义 + 用户绑定 + channel 绑定
  im_user_store.py       ←   (platform, platform_user_id) → 内部 User；allowlist
  schedule_store.py      ←   SQLite 定时任务定义与状态
  config.py              ←   pydantic-settings；加载 .env + config/settings.yaml
  paths.py               ←   路径解析（FLEETENT_HOME > 仓库 > ~/.fleetent）
  observability/         ←   trace / log / usage / diagnostics / startup_diagnostics
  auth.py                ←   seed_builtin_admin；Bearer token 验证（ma- 前缀）
  db.py                  ←   SQLiteDatabase wrapper；transaction context manager
```

---

## 关键设计决策

| 决策 | 结论 | 理由 |
|------|------|------|
| **运行时零 DB** | `agent.yaml` 文件索引驱动，agent_config.py 无 DB 查询 | 消除运行时 DB 依赖，热重载零停机 |
| **控制面/运行面分离** | `server.py` 不含 IM/loop/sandbox；`agent_app.py` 独立进程 | 控制面升级不影响运行中的 agent |
| **模型路由** | `model/resolver.py` per-agent 策略；STANDARD_ROUTE_KEYS；fallback 链 | `model/router.py` 已删除，resolver 为终态 |
| **模块包化** | runtime/model/tools/skills/session/integrations 已全部包化 | 旧扁平模块留 re-export shim，后续统一清理 |
| **存储边界** | SQLite-first，手写 SQL，Alembic 管理 schema；named parameters | 禁止 ORM，禁止 `sqlite3.connect` 扩散到业务层 |
| **Session 存储** | JSON 文件 + asyncio.Lock；`.json.tmp → rename` 原子写 | 可调试，防损坏 |
| **工具审批** | asyncio.Event 门控；重启后 `cleanup_stale_approvals()` 清理孤儿 | 无轮询，优雅等待 |
| **工具 schema 类型系统** | `schema_builder.py` 由类型注解生成 JSON Schema（list/Optional/Literal/Annotated） | 工具签名即契约，参数描述/枚举随注解声明 |
| **工具可用性门控** | `@tool(availability=...)` 运行时谓词；`get_schemas()` 每次实时过滤 | 缺依赖的工具（如未配 SearXNG）不暴露给 LLM，不报错 |
| **双轨代码执行** | `run_code`（Docker 沙箱，不可信代码）vs `bash_exec`（宿主机 Shell，risk=high 审批） | 数据处理与运维操作分流，各自的隔离/信任边界清晰 |
| **结构化澄清** | `clarify` 经独立 `user_input_gate` 挂起 loop；IM 层按平台渲染 choices | 与审批门语义分离；无 IM 时降级为文字、超时安全 |
| **大输出溢出** | 工具结果 >50KB 写 spillover 文件，返回前 100 行 + read_file 提示；每日清理 | 不丢数据、不撑爆上下文，agent 可按需续读 |
| **代码执行隔离** | Docker CLI（当前）→ microsandbox microVM（v1.0 目标） | 每沙箱独立 Linux 内核，< 100ms 启动 |
| **MCP 工具命名** | `{server}__{tool}` 双下划线 | 避免与内置工具名冲突，来源可追溯 |
| **数据主权** | 所有服务自托管；永久禁止 Pinecone Cloud / OpenAI Embeddings API 等云托管专有服务 | 客户数据不出内网 |

---

## 存储 Schema（Alembic 迁移版本）

| 版本范围 | 覆盖内容 |
|---------|---------|
| 001–010 | im_tables、scheduled_tasks、traces、memory_items、reflection |
| 011–020 | knowledge_base、knowledge_sources、knowledge_source_states、memory_maintenance、skill_admin、model_provider、agent_kbs、connectors |
| 021–030 | session_meta、agent_admin_state、monitoring、agent_ownership |
| 031–040 | long_term_context_policies、memory_namespace、agent_versions、agent_features、plugins、allowed_skills |
| 041–052 | kb_connector_store（051）、kb_connector_custom（052）、agent-scoped model routes |

---

## 进行中的 OpenSpec Change

| Change | 状态 | 说明 |
|--------|------|------|
| `agent-credential-authoring` | 进行中 | agent 凭据管理 + platform agent lifecycle spec |
| `archive/2026-06-05-agent-scoped-model-routing` | 已归档 | model/resolver.py 实现已合入 main |
| `archive/2026-06-05-split-agent-knowledge-config` | 已归档 | knowledge_base/config.py 已合入 main |
| `archive/2026-06-06-builtin-tools-overhaul` | 已归档 | file/shell/web/interaction 工具 + schema_builder/availability/spillover；PR #130/#133 已合入 main |

---

## 端点速查

| 端点 | 协议 | 说明 |
|------|------|------|
| `POST /chat` | HTTP SSE | 流式聊天（Bearer 认证） |
| `WebSocket /ws` | WS | TUI 客户端协议（JSON-RPC 2.0） |
| `POST /webhook/{source_id}` | HTTP | Webhook 事件接入 |
| `GET /health` | HTTP | 健康检查 |
| `GET /users/ui` | HTTP | admin 登录页 |
| `/admin/*` | HTTP | 控制面管理 API（platform/） |
