# fleetent

**定位**：面向企业 on-premises 部署的 Lean Agent 平台。Python + FastAPI，无 AI 框架依赖，支持 Slack / Telegram / WhatsApp，数据不出内网。

**基础设施原则**：所有外部服务组件必须可自托管（self-hostable），数据不出客户内网。PostgreSQL、Redis、Qdrant、RabbitMQ 等有官方 Docker 镜像的基础设施组件均可引入；Pinecone Cloud、OpenAI Embeddings API 等云托管专有服务禁止使用。

---

## 不可逾越的规则

AI 和所有团队成员必须遵守。违反任何一条 = 违反流程，需要回退重来。

### Commit 规范

格式：`type(scope): 简短描述`（英文，动词开头，scope 可选）

type 只能是：`feat` / `fix` / `refactor` / `test` / `docs` / `chore`

**禁止**：`update`、`fix bug`、`wip` 等模糊描述；一次 commit 混入多个不相关改动。

### TDD Hard Gate

每个实现 task 必须严格按顺序执行，不可跳步：

1. **写测试** → 运行**最窄相关命令**（单测试/单文件，如 `uv run pytest <file>::<test> -x -q`）→ **必须看到红**（测试失败）
   - 若直接绿：测试写错了，回去修
2. **写实现** → 运行同一最窄命令 → **必须看到绿**
   - 若仍红：修到绿才能继续
3. 可选 refactor → 确保仍然绿

> Hard Gate 管的是「必须见红 → 见绿」的纪律，**不规定范围**：红绿循环用最窄命令求快；
> task / PR 收尾跑什么范围见「测试规范 · 何时跑什么」。

跳过任何一步 = 违反流程。

### OpenSpec 工作流

> **前置条件（不可跳过）**：所有工作流从 main 最新代码出发。开始前执行：
> ```bash
> git pull origin main
> ```

**1. opsx:propose** — 定义「做什么」

- 写 proposal.md、specs/、design.md（可选）、tasks.md
- tasks.md 中**测试任务必须在对应实现任务之前**：
  ```
  - [ ] 3.1 Write failing tests for X: ...
  - [ ] 3.2 Implement X to pass tests
  ```
- 所有 artifact review 通过后才能进入实施

**2. 建 worktree + 功能分支**

- worktree 统一放在 `.worktrees/<change-name>/`（已在 `.gitignore` 中忽略）
- 分支命名：`feat/<change-name>`
- 命令：`git worktree add .worktrees/<change-name> -b feat/<change-name>`

**3. opsx:apply** — 每个 task 强制 TDD（见上方 TDD Hard Gate）

- 完成后将该 task 标记为 `[x]`
- 跳过任何一步 = 违反流程

**4. opsx:archive** — 所有 checkbox 为 `[x]` 后，在**当前功能分支**归档并同步 specs

- 归档先于合并决策：archive 表示"实现完成"，spec 同步随同一分支进入后续 PR，便于一并 review
- 不是"已上线"——归档不代表已部署到 main

**5. 推送分支 + 清理 worktree**

- 推送：`git push origin feat/<change-name>`
- 清理前提（三条全满足）：分支已推送到 remote、worktree 干净、无未提交改动
- 清理命令：`git worktree remove .worktrees/<change-name>`
- 任一不满足不得清理 worktree，避免丢失未推送的工作

### Agent / Platform 解耦

**核心架构契约**：agent 运行时与 platform 控制面**完全解耦**。agent 必须能在**没有 platform 的环境下独立运行**（`fleetent agent run`）；两者唯一的联系是 `agent.yaml` 和 `.env` 配置，不通过代码依赖或共享 platform 数据表耦合。

依赖方向（单向，不可逆）：

```
platform（管理入口） ──→ agent runtime（被启停、被读取）
agent runtime ──✗──→ platform        # 严格禁止反向依赖
```

- **agent 运行时模块**（`runtime/`、`session/`、`im_gateway/`、`tools/`、`integrations/`、`model/`、`observability/`、`governance/`、`memory/`、`long_term_ctx/`、`reflection/`）MUST NOT `import fleetent.platform.*`，也不得调用 platform 模块来触发行为
- **独立组件 / 基础设施**（`knowledge_base/` = 独立组件、`vector_store/` = 基础设施、`structured_logging.py` = 跨域日志底座）同样 MUST NOT `import fleetent.platform.*`，但理由不是"属 agent 运行时"，而是它们是自包含的独立组件 / 基础设施；`structured_logging` 被 agent runtime 与 platform 共同消费（被消费、不反向依赖业务或控制面），定位等同 `vector_store`，故为顶层基础设施而非 agent 运行时业务
- **agent 运行时产生的数据**（会话历史、压缩/token/恢复等元数据、运行轨迹）只能落到 agent 侧：session 文件、agent 侧 store、observability trace。**严禁写入 platform 的管理表**（如 `platform/chat_management` 的 `session_meta`）
- platform 需要 agent 数据时，**读** agent 侧产物（trace / session 文件 / agent store），而非要求 agent 反向写入 platform 表
- **验证基线**：任何改动后，agent 必须能在「无 platform、platform 的 DB 表不存在」的环境下完成 `fleetent agent run` 对话，相关功能不得依赖 platform 表才能工作
- **KB 读写边界**：`knowledge_base.retrieval`（agent 消费侧）MUST NOT import `knowledge_base.ingest`（platform 驱动侧）——retrieval ✗→ ingest，由依赖护栏测试强制

**归属判据（agent 能力 vs 控制面）**——判断一个能力归 agent 侧还是 platform 控制面，靠以下三条，不靠"在不在对话回合里"：

1. **关于自己 vs 外部对它**：能力是 agent「关于自己」（记忆 / 反思 / 上下文）还是「外部对它的管理」决定归属；时间尺度（同步 / 异步、在不在对话回合）**不决定**归属
2. **审批门 ≠ 归控制面**：一个能力即使其「变更」需人工审批门，能力本体仍归 agent 侧；审批门是横切治理（governance），变更 / 审批的管理 API 才是 platform 的薄暴露面
3. **自进化是纵向元能力**：reflection 不与 memory / retrieval 平铺，而是纵向贯穿各能力域——读 trace / memory / KB，产出对 user-memory / shared-memory / KB / skill 的改进建议，经统一审批门落地

**自进化的写经统一审批门**：所有自进化「写」经 `governance` 统一审批门落地（与 `permission_gate` 同类）。区分**真相源**（memory / shared-memory / skill：经审批**直接写**）与**派生视图**（KB：**不直接写**——agent 贡献写 agent-curated 沉淀源 → connector sync 流入 KB，保证 KB 始终是数据源的纯派生、可追溯；KB 写入路径单一，只 ingest / sync）。KB connector 外部摄取属受信运维，不经审批门

> 反例（已发生并返工）：把 compaction / token / resume_pending 写进 `session_meta`——agent 独立运行时该表不存在，功能静默失效。正确做法：状态存 session 文件 `meta` 字段，统计读 observability trace（`observability/usage.py`）。
>
> agent→platform 依赖现状（2026-06-10 复核）：`im_gateway/telegram`、`tools/builtin_tools` 早期那两处 import `platform.*` **已清理**（现无）。`permission_gate` 也已停止 import `user_store`（审批移 agent 侧 `approval_store`）。**仍存一处根因**：`user_store.authenticate` 仍 import `platform.user_management.api_key_store`——由 **#4 Identity 端口**结构性根除（认证下沉为基座端口，核只消费已解析的 Principal，详见 `docs/architecture/target-architecture-proposal.md §6`）。不得新增同类反向依赖。

---

## 架构

模块化单体，每个模块一个职责，边界清晰。

```
src/fleetent/
  # ── 平台控制面 ──
  platform/
    admin_cli/                    ← CLI 管理命令（fleetent-admin 入口）
    agent_lifecycle/              ← Agent 进程启停控制
    agent_management_console/     ← Agent 版本/绑定管理 + 生命周期控制台 API
    agent_statistics/             ← Agent 统计信息 API
    askit_console/                ← Agent 定义幂等应用 API
    chat_management/              ← 聊天会话管理和治理 API
    connector_management/         ← 连接器/MCP 管理 API
    im_gateway_management/        ← IM 网关管理 API
    knowledge_base_management/    ← 知识库管理和绑定 API
    model_provider_management/    ← 模型提供商管理 API
    skill_management/             ← Skill 管理和上传 API
    user_management/              ← 用户/API key 管理 API

  # ── Agent 运行时 ──
  runtime/
    loop.py              ← while tool-use 核心循环；run() + run_stream()
    context.py           ← in-session token 压缩，keep_tail identity check
    snapshot.py          ← agent 快照 load_active
    sub_agent.py         ← asyncio.gather 并行子 agent；最大深度 1
    agent_app.py         ← 单机 Agent 运行时启动（fleetent agent run）
    agent_init.py        ← Agent 主目录脚手架生成
    {termination,loop_detector,budget,layered_budget,cancellation,
     message_hygiene,error_classifier,tool_guardrails,sub_agent_lifecycle}.py

  # ── Agent 运行时能力 ──
  memory/                  ← 用户记忆提取/存储/检索
  long_term_ctx/           ← 长期上下文构建（记忆 + 知识库注入）
  reflection/              ← 反思报告生成

  # ── 平台与组件基础设施 ──
  knowledge_base/          ← KB 检索/向量化/解析/持久化运行时
  vector_store/            ← 向量嵌入和重排运行时
  structured_logging.py    ← 跨域结构化日志底座（agent 与 platform 共同消费；顶层基础设施）

  # ── 治理 ──
  governance/
    agent_policy.py      ← fnmatch tool 访问检查（allowed_tools 白名单）
    permission_gate.py   ← 人工审批门（medium/high 风险；agent 主动外呼审批人，R1）
    approval_store.py    ← 审批请求 + 门状态持久化（agent 侧，R1）
    audit_log.py         ← 平台管理操作审计日志
    blocklist.py         ← 用户封禁和级联撤销
    # quota.py 已 v1 descope 删除（迁移 065）

  # ── 集成 ──
  integrations/
    mcp/client.py        ← MCP HTTP/stdio client；工具注册为 {server}__{tool}
    sandbox/             ← Docker 沙箱容器生命周期管理（run_code 工具后端）

  # ── 模型 ──
  model/
    resolver.py          ← task_type → provider 配置（OpenAI-compatible + fallback 链）
    provider_health.py   ← 提供商健康缓存和熔断

  # ── 可观测性 ──
  observability/
    traces.py            ← Agent 运行轨迹追踪（append-only）
    usage.py             ← 使用情况汇总查询
    diagnostics.py       ← 诊断信息导出和保留
    {performance,startup_diagnostics,pilot_verification}.py

  # ── 会话 ──
  session/
    manager.py           ← JSON session 持久化；per-session asyncio.Lock
    index.py             ← 会话元数据索引

  # ── IM 网关 ──
  im_gateway/
    normalizer.py        ← NormalizedMessage dataclass；统一路由 pipeline
    slack.py             ← slack-bolt Socket Mode 适配器
    slack_supervisor.py  ← 多 Slack 连接器生命周期管理
    telegram.py          ← python-telegram-bot polling 适配器
    access.py            ← IM 访问控制

  # ── 工具 ──
  tools/
    registry.py          ← @tool 装饰器、schema 构建、dispatch；访问控制
    builtin_tools.py     ← 内置工具（import fleetent.tools 即注册，副作用经包 __init__ 保留）
    plugin_loader.py     ← 外部插件动态加载
    {multimodal,vision_client,image_gen_client,result_truncation}.py

  # ── Skills ──
  skills/
    registry.py          ← 扫描 skills/，关键词匹配，注入 system prompt
    audit.py             ← Skill 审计

  # ── TUI ──
  tui/                   ← 交互式终端 TUI（agent 服务的又一客户端，前后端分离+协议）
    protocol.py          ← newline-delimited JSON-RPC 2.0 编解码 + 方法/事件常量
    transport.py         ← Transport 抽象 + WSTransport（peer-gone 分类）
    dispatch.py          ← 单 dispatch：send/abort/approve/session.*；run_stream→event
    backend.py           ← 客户端 GatewayBackend（websockets 连接、收发协程、重连钩子）
    render.py            ← rich 渲染（流式文本/工具面板/审批提示/状态行），Console 可注入
    commands.py          ← 斜杠命令解析 + prompt_toolkit Completer
    app.py               ← AppController + prompt_toolkit 主循环；fleetent-tui 入口

  # ── 顶层模块 ──
  server.py              ← FastAPI：POST /chat (SSE)，GET /health，@app.websocket("/ws")，Bearer 认证
  config.py              ← pydantic-settings；加载 .env + config/settings.yaml（仅 platform 字段）
  agent_config.py        ← AgentFile pydantic 定义；agent.yaml 加载和扫描
  paths.py               ← 路径常量（FLEETENT_HOME 解析优先级）
  db.py                  ← 数据库运行时边界层（Alembic + 连接管理）
  auth.py                ← 密码哈希和登录会话
  connectors.py          ← 工具 OAuth 凭证管理
  agent_store.py         ← agent 定义 + 用户绑定 + channel 绑定
  user_store.py          ← 用户/API key 持久化
  im_user_store.py       ← (platform, platform_user_id) → 内部 User；allowlist 管理
  cron_scheduler.py      ← APScheduler 定时任务；server 启动时初始化
  schedule_store.py      ← 定时任务定义与状态持久化
  webhook_router.py      ← Webhook 来源配置加载、签名验证、消息提取
```

### Forbidden Patterns

以下做法**明确禁止**，不需讨论：

- **禁止引入 AI 框架**：LangChain / LlamaIndex / LangGraph——直接调 SDK，不要框架抽象
- **禁止 ORM**：数据库策略是 SQLite-first，不是 SQLite-only；手写 SQL 通过 store 边界保持可审计
- **禁止扩散 SQLite 细节**：新增或改造数据库代码必须经过统一 DB runtime / store 边界，不得继续扩散 `sqlite3.connect`、`DB_PATH` re-export、SQLite 专属方言到业务层
- **SQL 参数规范**：store 层 SQL 使用 named parameters（如 `:user_id`），不要新增 `?` 占位符风格
- **schema lifecycle 双权威（按库分）**：**管理库表**（users/api_keys/audit_log/im_connectors/im_channel_allowlist/tenants/teams/scheduled_tasks/approvals-platform 等）**仅由 Alembic** 维护——不要在 store `_init_db()` 建表/补列。**agent 侧库表**（traces/memory_items/sessions/approvals-agent/reflection/KB 等）须脱离 alembic 单机自建：现状用 `ensure_schema()`、目标态用**结构化嵌入式 forward-only 迁移（Y，`user_version` 戳）**（详见 data-model §5.2）。不得用裸 `sqlite3.connect` 绕过统一 `db.py`。
- **禁止全局可变状态**：legacy 模块级路径常量（`DB_PATH` / `SESSIONS_DIR` 等）在迁移前必须可通过 `monkeypatch` 注入，方便测试隔离
- **禁止 agent 运行时反向依赖 platform**：`runtime/`、`session/`、`im_gateway/`、`tools/`、`integrations/`、`knowledge_base/`、`memory/`、`reflection/`、`long_term_ctx/` 等 agent 运行时模块不得 `import fleetent.platform.*`，不得写入 platform 管理表；agent 必须可脱离 platform 独立运行（详见「Agent / Platform 解耦」）
- **新依赖必须经过讨论**：区分三类——
  - 基础设施服务（PostgreSQL、Redis、Qdrant 等）：可引入，需在 PR 中说明必要性和自托管方案
  - AI 框架（LangChain / LlamaIndex / LangGraph）：永久禁止，无论何种理由
  - 云托管专有服务（Pinecone Cloud、OpenAI Embeddings API 等）：永久禁止，违反数据主权原则

---

## 数据目录

**双 schema 权威（现状·单库）**：今天仍是单 `fleetent.db`。**管理表**由 Alembic 维护——`users`/`api_keys`/`audit_log`/`im_connectors`/`im_channel_allowlist`/`tenants`/`teams` 等已**全部入 alembic**（迁移至 069，store 不再 `_init_db` 建表）。**agent 侧表**为支持单机脱离 alembic 启动,由各 store `ensure_schema()` 自建、DDL 与 alembic head 一致（漂移护栏强制）；**目标态改用嵌入式迁移（Y，§5.2）**。**目标拓扑 = 5 物理库 + 按主体(tenant)物理分区**（管理 / per-agent / 共享记忆 / KB / 向量，见 `docs/architecture/data-model.md §5.1 / §5.7`），由 #3 落地。

```
data/  （现状单库；目标 5 物理库见 data-model §5.1，按主体物理分区见 §5.7）
  fleetent.db                     # gitignored
    ├── users / im_users / agents / user_agents / channel_agents       # 管理表（alembic）
    ├── api_keys / audit_log / im_connectors / im_channel_allowlist     # 管理表（alembic，v1 收编）
    ├── tenants / teams                                                 # 多租户根实体（alembic，迁移 067-069）
    ├── scheduled_tasks                                                 # 管理表（alembic）
    ├── traces / memory_items / sessions                               # agent-side（ensure_schema→嵌入式迁移 Y）
    ├── approvals                                                       # agent-side（governance/approval_store，R1）
    ├── knowledge_bases / knowledge_documents / knowledge_chunks        # agent-side（KB）
    └── reflection_reports / kb_reflection_reports / skill_proposals    # agent-side（自进化）
  users/{user_id}/memories.jsonl  # per-user 记忆（当前实现，v1.0 前迁移到 memory_items）
```

测试用 `tmp_path + monkeypatch` 隔离，绝不触碰 `data/`。但 `tmp_path` 不决定测试层级：只要创建真实 DB file、验证 schema、执行 CRUD 或 store/runtime 协作，就属于 integration。

**路径解析**：`config/` 与 `data/` 的实际位置由 `src/fleetent/paths.py` 统一解析（所有路径常量从 `config_dir()`/`data_dir()` 派生，禁止各模块自读家目录环境变量）。优先级：① `FLEETENT_HOME` 环境变量显式设置 → `$FLEETENT_HOME/{config,data}`；② 否则检测到仓库标记（CWD 含 `pyproject.toml` 的 `name="fleetent"` 或 `./config`）→ 仓库本地 `./config`+`./data`（**开发态零改动**）；③ 否则回退 `~/.fleetent/{config,data}`（全局安装态）。测试整体重定向可用 `monkeypatch.setenv("FLEETENT_HOME", tmp_path)`；只读 legacy shim / public API / path constant 兼容断言可直接检查常量或 monkeypatchability，但不得创建真实 DB。

**Agent 配置加载**：部署的单体 agent 读 home 根的 `agent.yaml`（`paths.agent_file() = base_dir()/agent.yaml`，扁平、无 `config/`）。`agent_config.build_index()`：当 `agents_dir`/`FLEETENT_AGENTS_DIR` 均未指定且 home 根存在 `agent.yaml` 时，加载它为**唯一且强制 default** 的 agent（跳过目录名校验）；否则回退扫描 `config/agents/<name>/`（多 agent，平台/dev 用）。

---

## 测试规范

### 隔离模式

- `conftest.py` 的 autouse `_isolate_fleetent_home` 把 `FLEETENT_HOME` 钉在临时目录——防止任何测试经 `~/.fleetent` 家目录回退泄漏到真实用户家目录（chdir 出仓库 + 未设 FLEETENT_HOME 时会触发）。测路径解析优先级的测试用自身 `monkeypatch` 覆盖它
- 数据库测试必须放在 `tests/integration/`，并使用统一 DB fixture 或 `tmp_path` 隔离；unit 只允许 mock 数据库或只读兼容断言
- `monkeypatch.setattr(memory_layer, "_mem_path", ...)` — 记忆文件隔离
- `patch("fleetent.memory_layer.get_client_and_config", ...)` — LLM 调用隔离
- 所有 async 测试自动收集：`asyncio_mode = auto`（pytest.ini），无需 `@pytest.mark.asyncio`

### Mock 策略

- **LLM 调用必须 mock**：patch `get_client_and_config`，单元测试不允许真实 API 调用
- **数据库必须隔离**：真实 DB file、schema、CRUD 或 store/runtime 协作测试放在 integration，并使用 `tmp_path` / 统一 DB fixture
- **文件路径必须隔离**：sessions、memories 路径同上
- **外部 HTTP**（MCP、sandbox）：用 `respx` 或 `unittest.mock` mock，不发真实请求

### 测试文件约定

- 测试按成本和依赖范围分层：
  - `tests/unit/`：单模块行为，mock LLM、数据库、HTTP、sandbox 等外部依赖，作为新增单元测试默认位置
    - unit 不得使用 FastAPI `TestClient` / app lifespan，不得运行 Alembic migration，不得导入
      `tests.integration.*` helper，也不得验证真实 SQLite schema lifecycle / DB runtime orchestration
    - unit 不得导入 `sqlite3`、monkeypatch `DB_PATH` 后创建真实 DB file、调用生产 `_init_db()`，也不得用
      `DATABASE_URL=sqlite:///...` 或 `create_database("sqlite:///...")` 验证 store/runtime 持久化
    - `tmp_path` 只可用于纯解析、配置路径、序列化和可注入文件边界；一旦用于真实 DB file、schema、CRUD 或 store/runtime 协作，测试必须放在 integration
    - 只读 legacy shim / public API / path constant 兼容断言可留在 unit
  - `tests/integration/`：多模块协作、SQLite/Alembic/FastAPI、observability trace / usage / logging 等需要真实本地组件的测试
    - FastAPI `TestClient`、Alembic migration、migrated SQLite tables、store/runtime wiring 都属于 integration
  - `tests/e2e/`：启动服务或走 CLI/HTTP/IM 完整链路的端到端测试；默认不进入 PR 门禁，真实服务 smoke 需显式开启
  - `tests/evaluation/`：memory、reflection、long-term context、knowledge-base 等效果评估；不得接入真实 LLM / embedding 服务作为默认测试
- 历史平铺测试已迁移到分层目录；不得继续向 `tests/` 根目录新增 `test_*.py`
- 命名：`test_{模块名}.py`，一模块一文件
- 每个测试函数只测一个行为，不在同一函数里断言多个不相关的事情
- `permission_gate` 测试必须传短超时：`PermissionGate(medium_timeout=0.1)`

### 何时跑什么（测试范围）

| 时机 | 命令 | 判据 |
|------|------|------|
| TDD 红/绿每一步 | `uv run pytest <file>::<test> -x -q`（最窄） | 见红 / 见绿 |
| 单个 task 收尾 | 受影响那一层：`uv run pytest tests/unit -q`（或 `tests/integration -q`） | 该层无新增失败 |
| change / PR 收尾 | `make test-pr`（unit〔除 quarantine〕+ 层边界 + **改动文件的** ruff format/lint，硬门禁必须全绿）＋ `uv run pytest tests/integration -q` 对照 main 基线 | test-pr 全绿；integration **不得引入新增失败** |
| e2e / evaluation | `make test-e2e` / `make test-evaluation` | 仅显式需要时手动跑，不进默认门禁 |

- **门禁判据是「无新增失败」，不是「零失败」**：当前（2026-06）约有 **2 个 unit + 19 个 integration** 预先存在失败，均属 `permission_gate` / agent-access 重构遗留（owner 非测试改动者）：
  - 2 个 unit（`test_loop_permission_gate.py`，permission_gate approvals 共享状态导致 flaky）已在 `make test-pr` 用 `--deselect` **quarantine**，owner 修复后移除该清单；plain `uv run pytest tests/unit` 仍会暴露它们。
  - integration 收尾用**不带 `-x`** 的 `uv run pytest tests/integration -q` 取完整失败集，与 `main` 对比，只确认没有**新增**失败。`-x` 只用于红绿循环（首个失败即停）。
- **`make test-pr` 的 ruff 只扫本分支 changed-vs-main 的 `.py`**：main 还带有约 36 个预先存在 lint + 2 个未格式化文件（分散在他人模块），全树 ruff 门禁不可行，你只对自己改过的文件负责。
- 裸 `uv run pytest` 会连 e2e / evaluation 一起跑（起真实服务 / 真 LLM），**不是 PR 门禁命令**；门禁用 `make test-pr` ＋ integration 基线对比。
- 涉及测试归位、测试层规则或新增 unit 测试时收尾跑 `uv run python scripts/check_test_layers.py`（已含在 `make test-pr`）。

---

## 代码风格

- **行长**：100（ruff 强制）
- **类型注解**：mypy strict，所有公开函数必须有完整注解
- **格式化**：提交前运行 `uv run ruff format src tests && uv run ruff check src tests`
- **注释**：只写"为什么"，不写"做什么"；好命名能表达的不加注释
- **Docstring**：Google 风格，只在公开 API 上写，内部函数不需要
- **异常**：不吞异常，catch 后必须 log 或 re-raise
- **新模块结构**：顶部 import → 常量（可注入路径/配置）→ 数据类 → 函数

---

## 常用命令

```bash
uv sync                          # 安装依赖
make test-pr                     # PR 门禁：unit〔除 quarantine〕+ 层边界 + 改动文件 ruff（必须全绿）
uv run pytest                    # 运行全部 4 层（含 e2e/evaluation，起真实服务，非门禁命令）
uv run pytest -x -q              # fail-fast，仅 TDD 红绿循环用
uv run pytest tests/unit         # 单元测试
uv run pytest tests/integration  # 集成测试（收尾对照 main 基线，确认无新增失败）
uv run pytest tests/e2e          # 端到端测试
uv run pytest tests/evaluation   # 效果评估测试
uv run python scripts/check_test_layers.py  # 检查 unit/integration 测试层边界
uv run ruff check src tests      # lint
uv run mypy src                  # 类型检查
uv run fleetent "hello"        # CLI
uv run fleetent-admin create-user --name "Alice"  # 用户管理
uvicorn fleetent.server:app --reload --port 8765  # HTTP 服务（默认端口 8765）
uv run fleetent-tui --token ma-<key>              # 交互式终端 TUI（连 /ws，默认本地 server）
```

---

## 环境变量

```
# Platform
DATABASE_URL           # 可选，默认 sqlite:///<data_dir>/fleetent.db
LOG_FORMAT             # console | json，默认 console

# Agent 运行时（agent.yaml 中配置；以下为进程级覆盖）
FLEETENT_HOME          # 覆盖 config/data 家目录（未设时：仓库内→./；仓库外→~/.fleetent）
FLEETENT_AGENTS_DIR    # 覆盖 agents 目录（默认 <config_dir>/agents）
FLEETENT_SKILLS_DIR    # 覆盖 skills/ 目录（默认 ./skills）
FLEETENT_PLUGINS_DIR   # 覆盖 plugins/ 目录

# TUI
FLEETENT_TUI_URL       # WebSocket 地址，默认 ws://127.0.0.1:8765/ws
FLEETENT_TOKEN         # Bearer token（--token 参数优先）
```

---

## Gotchas

- 路径常量（`DB_PATH`/`SESSIONS_DIR`/`SETTINGS_YAML_PATH` 等）在 import 时从 `paths.py` 求值一次（`paths.data_dir()/...`）——`FLEETENT_HOME` 须在进程启动前设定。测试中要在 import 后整体重定向，需 `monkeypatch.setenv("FLEETENT_HOME", ...)` 后 `importlib.reload(module)`，或直接 `monkeypatch.setattr(module, "<CONST>", ...)`（沿用既有注入习惯）。依赖 CWD-相对路径 + `chdir` 的旧测试在迁移后失效，改用常量注入
- `tools/builtin_tools.py` 注册工具是 import 副作用——`tools/__init__.py` 顶部 `from fleetent.tools import builtin_tools` 承载此副作用，`runtime/loop.py` 顶部 `import fleetent.tools` 触发注册，否则 `get_schemas()` 返回空
- `skills/registry.scan()` 在服务启动时运行（FastAPI lifespan），不是每次请求；CLI `run()` 每次调用
- `runtime/context.py` 的 `_keep_tail()` 用 identity check（`m is tail[0]`），不用 `==`——内容相同的 dict 相等但非同一对象（旧路径 `context_mgr` 留 shim；测试 patch/私有名访问改指 `fleetent.runtime.context`）
- runtime 旧扁平路径（`agent_loop`/`context_mgr`/`agent_runtime`/`sub_agent`/`cancellation` 等 13 个）仅留 re-export shim；测试 `patch`/`monkeypatch.setattr` 目标须打在 `fleetent.runtime.loop` 等真实子模块上——`import *` 复制引用，patch shim 不生效
- Bearer token 格式：`Authorization: Bearer ma-<64hex>`——`ma-` 前缀区分服务 key 与模型 API key
- `model/resolver.py` 每次调用新建 client——故意的，client 无状态且廉价
- `governance/permission_gate` 测试需要短超时：`PermissionGate(medium_timeout=0.1)`
- MCP 工具名用双下划线：`{server_id}__{tool_name}`——单下划线是工具名的一部分
- `session/manager.py` 原子写：`.json.tmp → rename`；测试中 monkeypatch `session_mgr.SESSIONS_DIR`
