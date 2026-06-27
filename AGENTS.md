# fleetent

面向企业 on-premises 部署的 Lean Agent 平台。Python + FastAPI，无 AI 框架依赖，支持 Slack / Telegram / WhatsApp，数据不出内网。

**基础设施原则**：所有外部服务组件必须可自托管。有官方 Docker 镜像的组件（PostgreSQL、Redis、Qdrant、RabbitMQ 等）可引入；云托管专有服务（Pinecone Cloud、OpenAI Embeddings API 等）禁止使用。

---

## 不可逾越的规则

AI 和所有团队成员必须遵守。违反任何一条 = 违反流程，需要回退重来。

### 语言

- 默认使用中文和用户交流。
- OpenSpec 产物（proposal.md、design.md、tasks.md、spec 文件）用中文写。
- 代码、commit message、API 字段、错误码使用英文。

### Commit 规范

格式：`type(scope): 简短描述`（英文，动词开头，scope 可选）。type 仅限 `feat` / `fix` / `refactor` / `test` / `docs` / `chore`。

禁止：`update`、`fix bug`、`wip` 等模糊描述；一次 commit 混入多个不相关改动。

### TDD Hard Gate

每个实现 task 必须严格按顺序，不可跳步：

1. **写测试** → 跑**最窄相关命令**（`uv run pytest <file>::<test> -x -q`）→ **必须见红**（若直接绿：测试未覆盖目标行为，先修测试）
2. **写实现** → 跑同一命令 → **必须见绿**
3. 可选 refactor → 确保仍绿

Hard Gate 只管「见红 → 见绿」纪律，**不规定范围**；task / PR 收尾的跑测范围见「测试规范 · 何时跑什么」。

### 非代码产物提交

TDD Hard Gate 只管代码实现；文档、proposal.md、design.md、tasks.md 等非代码产物由 agent 起草后，须**人工确认内容正确**再 commit，不得由 agent 直接提交。

### OpenSpec 工作流

> **前置条件**：所有工作流从 main 最新代码出发，开始前 `git pull origin main`。

1. **opsx:propose** — 写 proposal.md、specs/、design.md（可选）、tasks.md；tasks.md 中**测试任务必须在对应实现任务之前**
2. **建 worktree + 功能分支** — `git worktree add .worktrees/<change-name> -b feat/<change-name>`
3. **opsx:apply** — 按 task 执行，每个 task 强制 TDD；完成后标记 `[x]`
4. **opsx:archive** — 所有 checkbox 为 `[x]` 后，在**功能分支**归档并同步 specs（archive = "实现完成"，非"已上线 main"）。若 specs 已先经 **opsx:sync** 单独同步，archive 仅做归档移动
5. **推送 + 清理 worktree** — 前提：分支已推送 remote、worktree 干净、无未提交改动；之后再决定 merge / PR

**proposal / design 进入 implementation 前必须声明模块边界影响**：owning package、public API surface、owned tables（无则写无）、config namespace（无则写无）、cross-module dependencies、migration / shim plan。

### Agent / Platform 解耦（核心架构契约）

部署上 **platform 始终在场**；`fleetent agent run` 是 **node 拉起 agent 的原语**，也可供 dev/test 直接运行，**不是 standalone 部署模式**。依赖方向**单向不可逆**：

```
platform（管理入口） ──→ agent runtime（被启停、被读取）
agent runtime ──✗──→ platform        # 严格禁止反向依赖
```

- **agent 运行时模块**（`runtime/`、`session/`、`im_gateway/`、`tools/`、`integrations/`、`model/`、`observability/`、`governance/`、`memory/`、`long_term_ctx/`、`reflection/`）和**独立组件 / 基础设施**（`knowledge_base/`、`vector_store/`、`structured_logging.py`）MUST NOT `import fleetent.platform.*`。`im_gateway/` 是 **no-platform-import edge face**；managed 下执行宿主=node、身份 resolver 注入方=node，但 normalizer/loop 仍留在 agent。
- **KB 读写边界**：`knowledge_base.retrieval` MUST NOT import `knowledge_base.ingest`（护栏强制）
- agent 运行时产生的数据（会话历史、压缩/token/恢复元数据、运行轨迹）只能落 agent 侧（session 文件、agent store、observability trace），**严禁写入 platform 管理表**；platform 需要时读 agent 侧产物，不要求反向写入
- **验证基线**：任何改动后，agent 必须能在「无 platform、platform 的 DB 表不存在」环境下完成 `fleetent agent run` 对话

> 解耦机制：`user_store.authenticate` 经注入的 `_api_key_resolver` 解耦（platform 启动 `set_api_key_resolver` 注入，standalone agent 留 None）。护栏 `tests/unit/test_module_dependency_guardrails.py` 的 `_KNOWN_TRANSITIVE_PLATFORM_LEAKS` 为空集——任何新增的 agent→platform 传递泄漏都会 fail。不得新增同类反向依赖。

### 异步资源生命周期（owner-task 契约）

长生命周期异步资源（网络连接、SDK 会话、子进程流）**必须有唯一 owner task**：**谁打开谁关闭**——enter 和 exit 在同一 task 内（anyio cancel scope / task group 硬性要求）。跨 task 只传**句柄**（供消费），不传生命周期操作。**禁止用模块级全局单例持有活资源**（如模块级 `AsyncExitStack` 装连接）：它由"谁先用"的 task enter、却在关停时被另一 task 解栈，必然违反 task 亲和性并在 teardown 崩溃整个进程。关停链每一步必须**舱壁化**（独立 try/except + 超时），单组件收尾失败只记日志、不改退出码、不波及其它组件；优雅排水路径必须 exit 0。

> 范式实现：IM 连接 supervisor（每连接一个 owner task，`stop()` 定向取消）、MCP 会话宿主（`integrations/mcp/client.py` 的 `_SessionHost` + `aclose_all()`）。护栏 `test_no_module_level_asyncexitstack_singleton` 强制「src 内零模块级 AsyncExitStack 单例」；函数内局部 `AsyncExitStack`（同 task、作用域内）不受限。

---

## 项目结构

代码在 `src/fleetent/`，模块化单体，每个顶层包一个职责：

```
src/fleetent/
  platform/          # 平台控制面（管理 API / CLI）
  node/              # 托管部署宿主：拉起 agent 进程、forwarder、IM-edge 宿主、reconcile
  runtime/           # agent 核心循环与生命周期
  memory/            # 用户记忆提取/存储/检索
  long_term_ctx/     # 长期上下文构建
  reflection/        # 反思报告生成
  knowledge_base/    # KB 检索/向量化/持久化
  vector_store/      # 向量嵌入和重排
  substrate/         # agent 侧关系存储可插拔后端抽象（被 db.py 消费）
  governance/        # 审批门 / 权限 / 审计
  integrations/      # MCP client / 沙箱（sandbox/ 可插拔后端：backends/docker.py + backends/microsandbox.py）
  model/             # 模型路由和提供商健康
  observability/     # trace / usage / diagnostics
  session/           # 会话持久化
  im_gateway/        # Slack / Telegram edge face（managed 宿主=node；standalone 宿主=agent）
  tools/             # 工具注册 / 内置工具
  skills/            # Skill 注册和注入
  builtin_skills/    # 内置 skill 包（如 getting-started）
  tui/               # 交互式终端 TUI
  structured_logging.py  # 跨域日志底座（顶层基础设施）
  server.py          # FastAPI 入口
  db.py              # 数据库运行时边界层
  agent_config.py    # agent.yaml 定义和加载
  paths.py           # 路径常量（统一优先级解析）
```

平铺 legacy 模块在被大幅触碰时迁移；旧 import 路径保留 re-export shim（shim 不承载业务逻辑）。

---

## 数据与 Schema 生命周期

**4 物理库 + 按主体物理分区**（详见 `docs/architecture/data-model.md`）：管理库（单库、跨主体，真实文件 `data/management.db`）+ per-agent 运行库（state，含 `agent_memory_items`）+ per-tenant KB 关系库 + 向量底座，多主体时按 `<tenant>/<agent_id>/` 目录物理隔离。

**双权威**：
- **管理表**（users/api_keys/tenants/teams/scheduled_tasks 等，管理库）→ 仅由 **Alembic** 维护，不在 store 中 `_init_db()` 建表
- **agent 侧表**（traces/memory_items/sessions/approvals/KB/reflection 等，per-agent / per-tenant 库）→ **嵌入式 forward-only 迁移**：每物理文件一份有序 `MIGRATIONS=[(ver,sql)]` + `PRAGMA user_version` + migrate-on-open + 版本闸（`agent_state_migrations.py`、`knowledge_base/core/migrations.py`），脱离 Alembic 单机自建

测试用 `tmp_path + monkeypatch` 隔离，绝不触碰 `data/`。

---

## 常用命令

```bash
uv sync                                                     # 安装依赖
make test-pr                                                # PR 门禁（unit + 层边界 + 改动文件 ruff，必须全绿）
uv run pytest <file>::<test> -x -q                          # TDD 红/绿每一步（最窄命令）
make test-unit                                              # 单元测试（= uv run pytest tests/unit -q）
make test-integration                                       # 集成测试（收尾对照 main 基线）
uv run pytest tests/e2e                                     # 端到端测试
uv run pytest tests/evaluation                              # 效果评估测试
uv run python scripts/check_test_layers.py                  # 检查 unit/integration 层边界（已含在 make test-pr）
PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py  # 检查跨包 internal import
uv run ruff format src tests                                # 格式化
uv run ruff check src tests                                 # lint
uv run mypy src                                             # 类型检查
uv run fleetent "hello"                                     # CLI agent
uvicorn fleetent.server:app --reload --port 8765           # HTTP 服务（默认端口 8765）
uv run fleetent chat --token ma-<key>                      # 交互式终端 TUI
POST /admin/service-principals  body: {"name": "Alice"}    # 用户管理
```

---

## 代码风格

- 行长 100（ruff 强制）；mypy strict
- 公开函数必须有完整类型注解；公开 API 用 Google 风格 docstring
- 注释只写"为什么"，不复述"做什么"
- 新模块结构：import → 可注入常量/配置 → dataclass → 函数
- 不吞异常，catch 后必须 log 或 re-raise
- 已迁移 package 的 internal 实现不得被其他 package import；跨模块调用必须走 public API

**禁止**：
- AI 框架（LangChain / LlamaIndex / LangGraph）—— 永久禁止
- ORM —— 手写 SQL，通过 store 边界保持可审计
- 云托管专有服务 —— 违反数据主权原则
- 绕过统一 `db.py` 边界（不得扩散 `sqlite3.connect`、`DB_PATH` re-export 到业务层）
- store 层新增 `?` 占位符风格 SQL（统一用 named parameters，如 `:user_id`）
- 不可注入的全局可变状态（legacy 路径常量在迁移前必须方便 `monkeypatch` 隔离）

---

## 测试规范

`asyncio_mode = auto`，async 测试无需 `@pytest.mark.asyncio`。

> flaky / order-dependent / 并行 race 测试的复现与修复手册见 `docs/records/testing/flaky-tests-playbook.md`（含 CI 不随机化顺序的风险分类、根因清单、conftest 复位模式、验收标准）。

### 测试分层

| 层 | 位置 | 规则 |
|----|------|------|
| unit | `tests/unit/` | mock LLM/DB/HTTP；不得用 FastAPI TestClient / Alembic / 真实 DB file |
| integration | `tests/integration/` | 多模块协作、SQLite/Alembic/FastAPI、真实本地组件 |
| e2e | `tests/e2e/` | 完整链路；默认不进 PR 门禁 |
| evaluation | `tests/evaluation/` | 效果评估；不得接入真实 LLM |

`tmp_path` 只用于纯解析/配置/序列化；一旦用于真实 DB/schema/CRUD，测试必须放 integration。不得继续向 `tests/` 根目录新增 `test_*.py`。

unit 禁止涉及真实 DB file、schema、CRUD 或 store/runtime 协作：禁用 FastAPI `TestClient` / app lifespan、跑 Alembic migration、导入 `tests.integration.*` helper、验证真实 SQLite schema lifecycle / DB runtime orchestration、`import sqlite3` 后建真实 DB file、调用生产 `_init_db()`、用 `DATABASE_URL=sqlite:///...` 指向持久路径。unit 只可覆盖只读 legacy shim / public API / path constant 级逻辑。

### 何时跑什么

| 时机 | 命令 | 判据 |
|------|------|------|
| TDD 红/绿每步 | `uv run pytest <file>::<test> -x -q` | 见红/见绿 |
| 单 task 收尾 | 受影响层（unit 或 integration） | 该层无新增失败 |
| change / PR 收尾 | `make test-pr` + `make test-integration-ci`（并行、无 coverage、`-n auto`，~1min） | 两者全绿 |

CI 门禁：PR 和 main push 路径并行跑三格——unit+coverage（`make test-unit-ci`，`--fail-under=76`）、frontend、integration（`make test-integration-ci`，零失败，无 coverage 插桩）。每日定时路径（`custom: integration-tests`）跑合并覆盖（`make test-coverage-ci`，`--fail-under=88`）。**integration 现在是合并前门禁**（2026-06-27 加，根因见 memory：此前 integration 只在每日定时跑，integration-only 破坏会"PR 绿、main 绿、次日定时红"）。

**门禁判据是「无新增失败」，不是零失败**：存在一批预先存在的失败（`permission_gate` / agent-access 重构遗留，owner 非测试改动者），其中 flaky 的 `test_loop_permission_gate.py` 已在 `make test-pr` 用 `--deselect` quarantine。`make test-pr` 的 ruff 只扫本分支 changed-vs-main 的 `.py`——你只对自己改过的文件负责。

### Mock 策略

- LLM：patch `get_client_and_config`
- 数据库：integration 层，`tmp_path` 或统一 DB fixture
- 外部 HTTP（MCP/sandbox）：`respx` 或 `unittest.mock`
- `permission_gate` 测试：`PermissionGate(medium_timeout=0.1)`
- `conftest.py` autouse `_isolate_fleetent_home` 把 FLEETENT_HOME 钉在临时目录；测路径优先级的测试用自身 monkeypatch 覆盖

---

## 环境变量

```
DATABASE_URL           # 可选，默认 sqlite:///<data_dir>/management.db
LOG_FORMAT             # console | json，默认 console
FLEETENT_HOME          # 覆盖 config/data 家目录（未设时：仓库内→./；仓库外→~/.fleetent）
FLEETENT_AGENTS_DIR    # 覆盖 agents 目录（默认 <config_dir>/agents）
FLEETENT_SKILLS_DIR    # 覆盖 skills/ 目录（默认 ./skills）
FLEETENT_PLUGINS_DIR   # 覆盖 plugins/ 目录
FLEETENT_TUI_URL       # WebSocket 地址，默认 ws://127.0.0.1:8765/ws
FLEETENT_TOKEN         # Bearer token（--token 参数优先）
```

不要提交真实配置或 secret：复制 `config/*.example.*` 后本地修改；API key、Slack/Telegram token、`.env` 留在本机。

---

## Gotchas

> 多数条目对应 `docs/architecture/*.md` 权威设计文档，这里只记触发陷阱的关键点。

- **工具注册**：`tools/builtin_tools.py` 经 import 副作用注册工具；`tools/__init__.py` 顶部 `from fleetent.tools import builtin_tools` 承载此副作用，`runtime/loop.py` 顶部 `import fleetent.tools` 触发注册，否则 `get_schemas()` 返回空
- **Skill 扫描**：`skills/registry.scan()` 服务启动时跑（FastAPI lifespan）；CLI `run()` 每次调用时扫描
- **Context identity check**：`runtime/context.py` 的 `_keep_tail()` 用 identity check（`m is tail[0]`），不用 `==`；patch 目标须指 `fleetent.runtime.context`，patch 旧 shim `fleetent.context_mgr` 不生效
- **Runtime shim**：旧扁平路径（`agent_loop`/`context_mgr`/`agent_runtime`/`sub_agent`/`cancellation` 等 13 个）仅留 re-export shim；`monkeypatch.setattr` 须指真实子模块（如 `fleetent.runtime.loop`），patch shim 不生效
- **Session 原子写**：`session/manager.py` 写 `.json.tmp → rename`；测试中 monkeypatch `session_mgr.SESSIONS_DIR`
- **路径常量**：`DB_PATH`/`SESSIONS_DIR` 等在 import 时从 `paths.py` 求值一次；测试整体重定向用 `monkeypatch.setenv("FLEETENT_HOME", tmp_path)` + `importlib.reload()`，或 `monkeypatch.setattr(module, "<CONST>", ...)`
- **Bearer token 格式**：`Authorization: Bearer ma-<64hex>`（`ma-` 前缀区分服务 key 与模型 API key）
- **MCP 工具名**：`{server_id}__{tool_name}`（双下划线）
- **model/resolver.py**：每次调用新建 client——故意的，client 无状态且廉价
- **统一文件交换区 `/exchange`**（`artifact_exchange.py`）：MCP server 产物经 `/exchange/<server_id>/<rel>` 寻址（与 `/workspace` 并列）。**隔离轴 = workspace scope key**（`scope_key = workspace_scope_key(...)`，SESSION→session_id / AGENT→agent_name），`tenant_id`/`user_id` **不是**文件隔离 key（仅审计）。归属校验集中在 `resolve(path, scope_key, approved)`：本 scope 放行 / 跨 scope 拒绝（唯一豁免=已过 permission gate 的 `approved`）。**接线陷阱**：`set_state_db`+`set_views_root` 在 `agent_app._init_agent_db_schema` 接线，未接线则台账休眠（register 抛 RuntimeError 被 best-effort 吞）。
- **MCP 会话宿主**：每个会话由 `_SessionHost`（`integrations/mcp/client.py`）专属 task 持有，transport/ClientSession 的 enter/exit 同 task（见上「owner-task 契约」）；`_active_sessions` 存 live `ClientSession` 供消费，`_session_hosts` 管生命周期，关停经 `aclose_all()`。测试用 stub `_transport_cm` + `ClientSession`。
- **Sandbox 可插拔后端**：`integrations/sandbox` = `BaseSandboxBackend` + `backends/docker.py`（默认）+ `backends/microsandbox.py`（需宿主 KVM/HVF + 预装 runtime，否则探测失败降级 OFF），经 `factory.create_backend` 按 `sandbox.backend` 选型，能力差异经 `BackendCapabilities` 门控（不用 isinstance）。`client.py` 是 `SandboxClient = DockerBackend` 的 shim——`monkeypatch` Docker 内部（如 `_KILL_GRACE_SECONDS`）须打在 `backends.docker`，打 shim 不生效。
- **Directed-reach 主动触达**（权威 `docs/architecture/directed-reach.md`）：`outbound_connectors.notify_user(user_id, ...)` 按内部 user_id 主动 DM。**agent 只发意图、不解析地址**：managed 下入队 `target_type="user_id"` 意图到 `im_outbound_queue`，node drain 经 `PlatformAddressResolver` 反查 `im_users` → fan-out 该用户所有绑定渠道（无绑定→只记日志）。非 node-managed（dev `agent run`）= no-op。
- **platform→node 转发寻址**：platform 拨 node forwarder（`platform/node_management/agent_transport.py`）的目标 host 优先级 = **`nodes.forward_host`（node 上报）→ `FLEETENT_FORWARDER_HOST_OVERRIDE`（platform env）→ `{node_id}.internal`（约定兜底，依赖外部 DNS）**；端口/协议（8786 / http+ws）不变。node 经**可选** env `FLEETENT_NODE_ADVERTISE_HOST` 在 status 心跳的 `forward_host` 上报本机可达地址（未设则不上报、回落兜底），platform 经 `node_store.set_forward_host`/`get_forward_host` 持久化于管理库 `nodes` 列。寻址读 platform 自有 `node_store`，**不让 `node/` 引入 DB**；`forwarder_contract.py` 纯函数保留作兜底。寻址优先级覆盖逻辑只在 `agent_transport`，unit/integration 测它时须 mock `node_store.get_forward_host`（否则撞真实管理库 `nodes` 表）。
- **KB connector 定时调度**：`platform/knowledge_base_management/kb_connector_sweep.py` 的 `sweep()` 由 platform `cron_scheduler` 定时跑（server.py lifespan 注册，id `__kb_connector_sync_sweep__`），扫 `kb_connectors` 中 enabled 且配了 `sync_interval_seconds`、到期者入既有队列（去重=入队即推进 `last_scheduled_sync_at`），worker drain 跑 `run_connector_sync`。schedule 字段在管理库（Alembic 101）。
