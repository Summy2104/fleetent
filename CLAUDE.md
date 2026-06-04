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

1. **写测试** → 运行 `uv run pytest -x -q` → **必须看到红**（测试失败）
   - 若直接绿：测试写错了，回去修
2. **写实现** → 运行 `uv run pytest -x -q` → **必须看到绿**
   - 若仍红：修到绿才能继续
3. 可选 refactor → 确保仍然绿

跳过任何一步 = 违反流程。

### OpenSpec 工作流

**1. opsx:propose** — 定义「做什么」

- 写 proposal.md、specs/、design.md（可选）、tasks.md
- tasks.md 中**测试任务必须在对应实现任务之前**：
  ```
  - [ ] 3.1 Write failing tests for X: ...
  - [ ] 3.2 Implement X to pass tests
  ```
- 所有 artifact review 通过后才能进入实施

**2. 建 worktree + 功能分支**

**3. opsx:apply** — 每个 task 强制 TDD（见上方 TDD Hard Gate）

- 完成后将该 task 标记为 `[x]`
- 跳过任何一步 = 违反流程

**4. opsx:archive** — 所有 checkbox 为 `[x]` 后，在**当前功能分支**归档并同步 specs

- 归档先于合并决策：archive 表示"实现完成"，spec 同步随同一分支进入后续 PR，便于一并 review
- 不是"已上线"——归档不代表已部署到 main

**5. 推送分支 + 清理 worktree**

- 清理前提（三条全满足）：分支已推送到 remote（或已建 PR）、worktree 干净、无未提交改动
- 任一不满足不得清理 worktree，避免丢失未推送的工作

**6. 后续决定 merge 或 PR** — 在主仓库基于已推送分支进行，与 worktree 生命周期解耦

---

## 架构

模块化单体，每个模块一个职责，边界清晰。

```
src/fleetent/
  runtime/loop.py          ← while tool-use 核心循环；run() + run_stream()（←agent_loop.py，旧路径留 shim）
  runtime/context.py       ← in-session token 压缩，keep_tail identity check（←context_mgr.py）
  runtime/snapshot.py      ← agent 快照 load_active（←agent_runtime.py）
  runtime/sub_agent.py     ← asyncio.gather 并行子 agent；最大深度 1
  runtime/{termination,loop_detector,budget,layered_budget,cancellation,message_hygiene,error_classifier,tool_guardrails,sub_agent_lifecycle}.py ← 运行治理（终止/循环检测/预算/取消/消息净化/错误分类/工具护栏/子 agent 生命周期）
  model_router.py    ← task_type → provider 配置（OpenAI-compatible + fallback 链）
  tools/registry.py        ← @tool 装饰器、schema 构建、dispatch；访问控制
  tools/builtin_tools.py   ← 内置工具（import fleetent.tools 即注册，副作用经包 __init__ 保留）
  skill_registry.py  ← 扫描 skills/，关键词匹配，注入 system prompt
  memory_layer.py    ← 跨 session 事实：Haiku 提取 → JSONL → 注入
  user_store.py      ← 用户/API key 持久化（当前 SQLite-first）
  eval_logger.py     ← append-only JSONL 追踪日志
  server.py          ← FastAPI：POST /chat (SSE)，GET /health，Bearer 认证
  admin.py           ← CLI：create-user, list-users, rotate-key 等
  config.py          ← pydantic-settings；加载 .env + config/settings.yaml
  agent_policy.py    ← fnmatch tool 访问检查（allowed_tools 白名单）
  agent_store.py     ← agent 定义 + 用户绑定 + channel 绑定（当前 SQLite-first）
  im_user_store.py   ← (platform, platform_user_id) → 内部 User；allowlist 管理
  session_mgr.py     ← JSON session 持久化；per-session asyncio.Lock
  permission_gate.py ← asyncio.Event 人工审批门（medium/high 风险）
  sandbox_client.py  ← Docker CLI 封装：隔离 Python 执行
  mcp_client.py      ← MCP HTTP/stdio client；工具注册为 {server}__{tool}
  cron_scheduler.py  ← APScheduler 定时任务；server 启动时初始化
  schedule_store.py  ← 定时任务定义与状态持久化（当前 SQLite-first）
  webhook_router.py  ← Webhook 来源配置加载、签名验证、消息提取
  im_gateway/
    normalizer.py    ← NormalizedMessage dataclass；统一路由 pipeline
    slack.py         ← slack-bolt Socket Mode 适配器
    telegram.py      ← python-telegram-bot polling 适配器
  tui/               ← 交互式终端 TUI(agent 服务的又一客户端，前后端分离+协议)
    protocol.py      ← newline-delimited JSON-RPC 2.0 编解码 + 方法/事件常量
    transport.py     ← Transport 抽象 + WSTransport(peer-gone 分类)
    dispatch.py      ← 单 dispatch：send/abort/approve/session.*；run_stream→event
    backend.py       ← 客户端 GatewayBackend(websockets 连接、收发协程、重连钩子)
    render.py        ← rich 渲染(流式文本/工具面板/审批提示/状态行)，Console 可注入
    commands.py      ← 斜杠命令解析 + prompt_toolkit Completer
    app.py           ← AppController + prompt_toolkit 主循环；fleetent-tui 入口
  server.py 另新增 @app.websocket("/ws") 挂接 tui dispatch(SSE /chat 不变)
```

### Forbidden Patterns

以下做法**明确禁止**，不需讨论：

- **禁止引入 AI 框架**：LangChain / LlamaIndex / LangGraph——直接调 SDK，不要框架抽象
- **禁止 ORM**：数据库策略是 SQLite-first，不是 SQLite-only；手写 SQL 通过 store 边界保持可审计
- **禁止扩散 SQLite 细节**：新增或改造数据库代码必须经过统一 DB runtime / store 边界，不得继续扩散 `sqlite3.connect`、`DB_PATH` re-export、SQLite 专属方言到业务层
- **SQL 参数规范**：store 层 SQL 使用 named parameters（如 `:user_id`），不要新增 `?` 占位符风格
- **schema lifecycle 归 Alembic**：不要在新 store 中复制 `_init_db()` 建表/补列模式
- **禁止全局可变状态**：legacy 模块级路径常量（`DB_PATH` / `SESSIONS_DIR` 等）在迁移前必须可通过 `monkeypatch` 注入，方便测试隔离
- **新依赖必须经过讨论**：区分三类——
  - 基础设施服务（PostgreSQL、Redis、Qdrant 等）：可引入，需在 PR 中说明必要性和自托管方案
  - AI 框架（LangChain / LlamaIndex / LangGraph）：永久禁止，无论何种理由
  - 云托管专有服务（Pinecone Cloud、OpenAI Embeddings API 等）：永久禁止，违反数据主权原则

---

## 数据目录

```
data/
  users.db                        # SQLite 主库 — gitignored
    ├── users / im_users / agents / user_agents / channel_agents
    ├── scheduled_tasks / approvals
    ├── traces                    # eval 日志（append-only，按 agent_id/user_id/时间可查）
    ├── memory_items              # per-user 语义记忆（v1.0，替换 memories.jsonl）
    ├── documents / chunks / chunks_fts / entities / relations  # knowledge_base（v1.0）
    └── skill_proposals / kb_reflection_reports                 # reflection（v1.0）
  users/{user_id}/memories.jsonl  # per-user 记忆（当前实现，v1.0 前迁移到 users.db）
```

测试用 `tmp_path + monkeypatch` 隔离，绝不触碰 `data/`。

**路径解析**：`config/` 与 `data/` 的实际位置由 `src/fleetent/paths.py` 统一解析（所有路径常量从 `config_dir()`/`data_dir()` 派生，禁止各模块自读家目录环境变量）。优先级：① `FLEETENT_HOME` 环境变量显式设置 → `$FLEETENT_HOME/{config,data}`；② 否则检测到仓库标记（CWD 含 `pyproject.toml` 的 `name="fleetent"` 或 `./config`）→ 仓库本地 `./config`+`./data`（**开发态零改动**）；③ 否则回退 `~/.fleetent/{config,data}`（全局安装态）。测试整体重定向可用 `monkeypatch.setenv("FLEETENT_HOME", tmp_path)`；单模块仍可 `monkeypatch.setattr(module, "DB_PATH", ...)`。

**Agent 配置加载**：部署的单体 agent 读 home 根的 `agent.yaml`（`paths.agent_file() = base_dir()/agent.yaml`，扁平、无 `config/`）。`agent_config.build_index()`：当 `agents_dir`/`FLEETENT_AGENTS_DIR` 均未指定且 home 根存在 `agent.yaml` 时，加载它为**唯一且强制 default** 的 agent（跳过目录名校验）；否则回退扫描 `config/agents/<name>/`（多 agent，平台/dev 用）。

---

## 测试规范

### 隔离模式

- `conftest.py` 的 autouse `_isolate_fleetent_home` 把 `FLEETENT_HOME` 钉在临时目录——防止任何测试经 `~/.fleetent` 家目录回退泄漏到真实用户家目录（chdir 出仓库 + 未设 FLEETENT_HOME 时会触发）。测路径解析优先级的测试用自身 `monkeypatch` 覆盖它
- 数据库测试优先使用统一 DB fixture 或 `tmp_path` 隔离；legacy store 迁移前可 `monkeypatch.setattr(module, "DB_PATH", tmp_path / "x.db")`
- `monkeypatch.setattr(memory_layer, "_mem_path", ...)` — 记忆文件隔离
- `patch("fleetent.memory_layer.get_client_and_config", ...)` — LLM 调用隔离
- 所有 async 测试自动收集：`asyncio_mode = auto`（pytest.ini），无需 `@pytest.mark.asyncio`

### Mock 策略

- **LLM 调用必须 mock**：patch `get_client_and_config`，单元测试不允许真实 API 调用
- **数据库必须隔离**：使用 `tmp_path` / 统一 DB fixture；legacy store 迁移前 monkeypatch `DB_PATH` 到 `tmp_path`
- **文件路径必须隔离**：sessions、memories 路径同上
- **外部 HTTP**（MCP、sandbox）：用 `respx` 或 `unittest.mock` mock，不发真实请求

### 测试文件约定

- 测试按成本和依赖范围分层：
  - `tests/unit/`：单模块行为，mock LLM、数据库、HTTP、sandbox 等外部依赖，作为新增单元测试默认位置
  - `tests/integration/`：多模块协作、SQLite/Alembic/FastAPI、observability trace / usage / logging 等需要真实本地组件的测试
  - `tests/e2e/`：启动服务或走 CLI/HTTP/IM 完整链路的端到端测试；默认不进入 PR 门禁，真实服务 smoke 需显式开启
  - `tests/evaluation/`：memory、reflection、long-term context、knowledge-base 等效果评估；不得接入真实 LLM / embedding 服务作为默认测试
- 历史平铺测试已迁移到分层目录；不得继续向 `tests/` 根目录新增 `test_*.py`
- 命名：`test_{模块名}.py`，一模块一文件
- 每个测试函数只测一个行为，不在同一函数里断言多个不相关的事情
- `permission_gate` 测试必须传短超时：`PermissionGate(medium_timeout=0.1)`
- TDD 红绿循环优先运行最近相关分层命令，例如 `uv run pytest tests/unit -x -q` 或 `uv run pytest tests/integration -x -q`；收尾必须运行 `uv run pytest -x -q`

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
uv run pytest                    # 运行测试
uv run pytest -x -q              # fail-fast
uv run pytest tests/unit         # 单元测试
uv run pytest tests/integration  # 集成测试
uv run pytest tests/e2e          # 端到端测试
uv run pytest tests/evaluation   # 效果评估测试
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
ANTHROPIC_API_KEY      # 默认路由必需
FLEETENT_HOME          # 覆盖 config/data 家目录（未设时：仓库内→./；仓库外→~/.fleetent）
FLEETENT_SKILLS_DIR  # 覆盖 skills/ 目录（默认 ./skills）
FLEETENT_AGENTS_DIR  # 覆盖 agents 目录（默认 <config_dir>/agents）
```

---

## Gotchas

- 路径常量（`DB_PATH`/`SESSIONS_DIR`/`SETTINGS_YAML_PATH` 等）在 import 时从 `paths.py` 求值一次（`paths.data_dir()/...`）——`FLEETENT_HOME` 须在进程启动前设定。测试中要在 import 后整体重定向，需 `monkeypatch.setenv("FLEETENT_HOME", ...)` 后 `importlib.reload(module)`，或直接 `monkeypatch.setattr(module, "<CONST>", ...)`（沿用既有注入习惯）。依赖 CWD-相对路径 + `chdir` 的旧测试在迁移后失效，改用常量注入
- `tools/builtin_tools.py` 注册工具是 import 副作用——`tools/__init__.py` 顶部 `from fleetent.tools import builtin_tools` 承载此副作用，`runtime/loop.py` 顶部 `import fleetent.tools` 触发注册，否则 `get_schemas()` 返回空
- `skill_registry.scan()` 在服务启动时运行（FastAPI lifespan），不是每次请求；CLI `run()` 每次调用
- `runtime/context.py` 的 `_keep_tail()` 用 identity check（`m is tail[0]`），不用 `==`——内容相同的 dict 相等但非同一对象（旧路径 `context_mgr` 留 shim；测试 patch/私有名访问改指 `fleetent.runtime.context`）
- runtime 旧扁平路径（`agent_loop`/`context_mgr`/`agent_runtime`/`sub_agent`/`cancellation` 等 13 个）仅留 re-export shim；测试 `patch`/`monkeypatch.setattr` 目标须打在 `fleetent.runtime.loop` 等真实子模块上——`import *` 复制引用，patch shim 不生效
- Bearer token 格式：`Authorization: Bearer ma-<64hex>`——`ma-` 前缀区分服务 key 与模型 API key
- `model_router.get_async_client_and_config()` 每次调用新建 client——故意的，client 无状态且廉价
- `permission_gate` 测试需要短超时：`PermissionGate(medium_timeout=0.1)`
- MCP 工具名用双下划线：`{server_id}__{tool_name}`——单下划线是工具名的一部分
- `session_mgr` 原子写：`.json.tmp → rename`；测试中 monkeypatch `session_mgr.SESSIONS_DIR`
