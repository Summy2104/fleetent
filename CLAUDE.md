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

**4. merge / PR，清理 worktree**

**5. opsx:archive** — 所有 checkbox 为 `[x]` 后归档，同步 specs

---

## 架构

模块化单体，每个模块一个职责，边界清晰。

```
src/fleetent/
  agent_loop.py      ← while tool-use 核心循环；run() + run_stream()
  model_router.py    ← task_type → provider 配置（OpenAI-compatible + fallback 链）
  tool_registry.py   ← @tool 装饰器、schema 构建、dispatch；访问控制
  tools.py           ← 内置工具（import 即注册，副作用）
  skill_registry.py  ← 扫描 skills/，关键词匹配，注入 system prompt
  context_mgr.py     ← in-session token 压缩，keep_tail identity check
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
  sub_agent.py       ← asyncio.gather 并行子 agent；最大深度 1
  cron_scheduler.py  ← APScheduler 定时任务；server 启动时初始化
  schedule_store.py  ← 定时任务定义与状态持久化（当前 SQLite-first）
  webhook_router.py  ← Webhook 来源配置加载、签名验证、消息提取
  im_gateway/
    normalizer.py    ← NormalizedMessage dataclass；统一路由 pipeline
    slack.py         ← slack-bolt Socket Mode 适配器
    telegram.py      ← python-telegram-bot polling 适配器
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

---

## 测试规范

### 隔离模式

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

- 命名：`tests/test_{模块名}.py`，一模块一文件
- 每个测试函数只测一个行为，不在同一函数里断言多个不相关的事情
- `permission_gate` 测试必须传短超时：`PermissionGate(medium_timeout=0.1)`

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
uv run ruff check src tests      # lint
uv run mypy src                  # 类型检查
uv run fleetent "hello"        # CLI
uv run fleetent-admin create-user --name "Alice"  # 用户管理
uvicorn fleetent.server:app --reload  # HTTP 服务（端口 8000）
```

---

## 环境变量

```
ANTHROPIC_API_KEY      # 默认路由必需
FLEETENT_SKILLS_DIR  # 覆盖 skills/ 目录（默认 ./skills）
```

---

## Gotchas

- `tools.py` 注册工具是 import 副作用——`agent_loop.py` 顶部必须 import，否则 `get_schemas()` 返回空
- `skill_registry.scan()` 在服务启动时运行（FastAPI lifespan），不是每次请求；CLI `run()` 每次调用
- `context_mgr._keep_tail()` 用 identity check（`m is tail[0]`），不用 `==`——内容相同的 dict 相等但非同一对象
- Bearer token 格式：`Authorization: Bearer ma-<64hex>`——`ma-` 前缀区分服务 key 与模型 API key
- `model_router.get_async_client_and_config()` 每次调用新建 client——故意的，client 无状态且廉价
- `permission_gate` 测试需要短超时：`PermissionGate(medium_timeout=0.1)`
- MCP 工具名用双下划线：`{server_id}__{tool_name}`——单下划线是工具名的一部分
- `session_mgr` 原子写：`.json.tmp → rename`；测试中 monkeypatch `session_mgr.SESSIONS_DIR`
