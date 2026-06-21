# fleetent

面向企业 on-premises 部署的 Lean Agent 平台。Python + FastAPI，无 AI 框架依赖，支持 Slack / Telegram / WhatsApp，数据不出内网。

**基础设施原则**：所有外部服务组件必须可自托管（self-hostable），数据不出客户内网。PostgreSQL、Redis、Qdrant、RabbitMQ 等有官方 Docker 镜像的组件均可引入；Pinecone Cloud、OpenAI Embeddings API 等云托管专有服务禁止使用。

---

## 不可逾越的规则

AI 和所有团队成员必须遵守。违反任何一条 = 违反流程，需要回退重来。

### 语言

- 默认使用中文和用户交流。
- OpenSpec 产物（proposal.md、design.md、tasks.md、spec 文件）用中文写。
- 代码、commit message、API 字段、错误码使用英文。

### Commit 规范

格式：`type(scope): 简短描述`（英文，动词开头，scope 可选）

type 只能是：`feat` / `fix` / `refactor` / `test` / `docs` / `chore`

禁止：`update`、`fix bug`、`wip` 等模糊描述；一次 commit 不要混入多个不相关改动。

### TDD Hard Gate

每个实现 task 必须严格按顺序执行，不可跳步：

1. **写测试** → 运行**最窄相关命令**（`uv run pytest <file>::<test> -x -q`）→ **必须看到红**（若直接绿：测试未覆盖目标行为，先修测试）
2. **写实现** → 运行同一命令 → **必须看到绿**
3. 可选 refactor → 确保仍然绿

Hard Gate 管「必须见红 → 见绿」纪律，**不规定范围**；task / PR 收尾跑什么范围见「测试规范 · 何时跑什么」。跳过任何一步 = 违反流程。

### 非代码产物提交

TDD Hard Gate 只管代码实现；文档、proposal.md、design.md、tasks.md 等非代码产物由 agent 起草后，须**人工确认内容正确**再 commit，不得由 agent 直接提交。

### OpenSpec 工作流

> **前置条件**：所有工作流从 main 最新代码出发，开始前执行 `git pull origin main`。

1. **opsx:propose** — 写 proposal.md、specs/、design.md（可选）、tasks.md；tasks.md 中**测试任务必须在对应实现任务之前**
2. **建 worktree + 功能分支** — `git worktree add .worktrees/<change-name> -b feat/<change-name>`
3. **opsx:apply** — 按 task 执行，每个 task 强制 TDD；完成后标记 `[x]`
4. **opsx:archive** — 所有 checkbox 为 `[x]` 后，在**功能分支**归档并同步 specs（archive 表示"实现完成"，不代表已上线到 main）。若 specs 已先经 **opsx:sync** 单独同步（实现先进 main、或并行切片的后续 propose 需要最新 specs 时），archive 仅做归档移动
5. **推送 + 清理 worktree** — 清理前提：分支已推送到 remote、worktree 干净、无未提交改动；之后再决定 merge / PR

**proposal / design 进入 implementation 前必须声明模块边界影响**：
- owning package（如 `runtime` / `platform` / `governance` / ...）
- public API surface（允许其他模块 import 的函数、dataclass、service interface）
- owned tables（新增或修改的持久化表；无则写无）
- config namespace（新增配置所属命名空间；无则写无）
- cross-module dependencies（依赖哪些模块 public API，是否触碰共享契约）
- migration / shim plan（移动平铺模块时如何保留 re-export 兼容）

### Agent / Platform 解耦（核心架构契约）

部署上 **platform 始终在场**；`fleetent agent run` 是 **node 拉起 agent 的原语**，也可供 dev/test 直接运行，**不是 standalone 部署模式**。依赖方向**单向不可逆**：

```
platform（管理入口） ──→ agent runtime（被启停、被读取）
agent runtime ──✗──→ platform        # 严格禁止反向依赖
```

- **agent 运行时模块**（`runtime/`、`session/`、`im_gateway/`、`tools/`、`integrations/`、`model/`、`observability/`、`governance/`、`memory/`、`long_term_ctx/`、`reflection/`）MUST NOT `import fleetent.platform.*`
- **独立组件 / 基础设施**（`knowledge_base/`、`vector_store/`、`structured_logging.py`）同样 MUST NOT `import fleetent.platform.*`
- **KB 读写边界**：`knowledge_base.retrieval` MUST NOT import `knowledge_base.ingest`（依赖护栏测试强制）
- agent 运行时产生的数据（会话历史、压缩/token/恢复元数据、运行轨迹）只能落 agent 侧（session 文件、agent store、observability trace），**严禁写入 platform 管理表**
- platform 需要 agent 数据时读 agent 侧产物，而非要求 agent 反向写入 platform 表
- **验证基线**：任何改动后，agent 必须能在「无 platform、platform 的 DB 表不存在」环境下完成 `fleetent agent run` 对话

> 现状（2026-06-11 审计后）：agent 运行时 + 独立组件对 platform 的反向 import **已彻底归零**。`user_store.authenticate` 经注入的 `_api_key_resolver` 解耦（platform 启动时 `set_api_key_resolver` 注入，standalone agent 留 None）。护栏 `tests/unit/test_module_dependency_guardrails.py` 的 `_KNOWN_TRANSITIVE_PLATFORM_LEAKS` 已清空（`= set()`）：任何新增的 agent→platform 传递泄漏都会 fail。不得新增同类反向依赖。

### 异步资源生命周期（owner-task 契约）

长生命周期异步资源（网络连接、SDK 会话、子进程流）**必须有唯一 owner task**：**谁打开谁关闭**——enter 和 exit 发生在同一个 task 内（anyio cancel scope / task group 的硬性要求）。跨 task 只传**句柄**（供消费），不传生命周期操作；**禁止用模块级全局单例持有活资源**（如模块级 `AsyncExitStack` 装连接）——它由"谁先用谁的 task"enter、却在关停时被另一个 task 解栈，必然违反 task 亲和性并在 teardown 时崩溃整个进程（2026-06-11 事故）。关停链上每一步必须**舱壁化**（独立 try/except + 超时），单组件收尾失败只记日志、不改变进程退出码、不波及其它组件；优雅排水路径必须 exit 0。

> 范式实现：IM 连接 supervisor（每连接一个 owner task，`stop()` 定向取消）、MCP 会话宿主（`integrations/mcp/client.py` 的 `_SessionHost` + `aclose_all()`）。护栏 `test_module_dependency_guardrails.py::test_no_module_level_asyncexitstack_singleton` 强制「src 内零模块级 AsyncExitStack 单例」。函数内局部 `AsyncExitStack`（同 task、作用域内）不受限。

---

## 项目结构

代码在 `src/fleetent/`，模块化单体，每个顶层包一个职责：

```
src/fleetent/
  platform/          # 平台控制面（管理 API / CLI）
  runtime/           # agent 核心循环与生命周期
  memory/            # 用户记忆提取/存储/检索
  long_term_ctx/     # 长期上下文构建
  reflection/        # 反思报告生成
  knowledge_base/    # KB 检索/向量化/持久化
  vector_store/      # 向量嵌入和重排
  governance/        # 审批门 / 权限 / 审计
  integrations/      # MCP client / 沙箱（sandbox/ 可插拔后端：backends/docker.py + backends/microsandbox.py）
  model/             # 模型路由和提供商健康
  observability/     # trace / usage / diagnostics
  session/           # 会话持久化
  im_gateway/        # Slack / Telegram 适配器
  tools/             # 工具注册 / 内置工具
  skills/            # Skill 注册和注入
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

**5 物理库 + 按主体物理分区已落地**（持久层 #3，详见 `docs/architecture/data-model.md`）：管理库（单库、跨主体）+ per-agent 运行库 + per-tenant 共享记忆库 / KB 关系库 + 向量底座，多主体时按 `<tenant>/<agent_id>/` 目录物理隔离。管理库真实文件为 `data/management.db`（存量部署的旧 `fleetent.db` 由 `scripts/upgrade.py` 在升级时重命名）。

**双权威**：
- **管理表**（users/api_keys/tenants/teams/scheduled_tasks 等，管理库）→ 仅由 **Alembic** 维护，不在 store 中 `_init_db()` 建表
- **agent 侧表**（traces/memory_items/sessions/approvals/KB/reflection 等，per-agent / per-tenant 库）→ **嵌入式 forward-only 迁移（Y）已落地**：每物理文件一份有序 `MIGRATIONS=[(ver,sql)]` + `PRAGMA user_version` + migrate-on-open + 版本闸（`agent_state_migrations.py`、`knowledge_base/core/migrations.py`、`memory/shared_memory_migrations.py`），脱离 Alembic 单机自建

测试用 `tmp_path + monkeypatch` 隔离，绝不触碰 `data/`。

---

## 常用命令

```bash
uv sync                                                     # 安装依赖
make test-pr                                                # PR 门禁（unit + 层边界 + 改动文件 ruff，必须全绿）
uv run pytest <file>::<test> -x -q                          # TDD 红/绿每一步（最窄命令）
uv run pytest tests/unit -q                                 # 单元测试
uv run pytest tests/integration -q                         # 集成测试（收尾对照 main 基线）
make test-unit                                              # 同上（make 快捷）
make test-integration                                       # 同上（make 快捷）
uv run pytest tests/e2e                                     # 端到端测试
uv run pytest tests/evaluation                              # 效果评估测试
uv run python scripts/check_test_layers.py                  # 检查 unit/integration 层边界（已含在 make test-pr）
PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py  # 检查跨包 internal import
uv run ruff format src tests                                # 格式化
uv run ruff check src tests                                 # lint
uv run mypy src                                             # 类型检查
uv run fleetent "hello"                                     # CLI agent
POST /admin/service-principals  # body: {"name": "Alice"}            # 用户管理
uvicorn fleetent.server:app --reload --port 8765            # HTTP 服务（默认端口 8765）
uv run fleetent chat --token ma-<key>                      # 交互式终端 TUI
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

### 测试分层

| 层 | 位置 | 规则 |
|----|------|------|
| unit | `tests/unit/` | mock LLM/DB/HTTP；不得用 FastAPI TestClient / Alembic / 真实 DB file |
| integration | `tests/integration/` | 多模块协作、SQLite/Alembic/FastAPI、真实本地组件 |
| e2e | `tests/e2e/` | 完整链路；默认不进 PR 门禁 |
| evaluation | `tests/evaluation/` | 效果评估；不得接入真实 LLM |

`tmp_path` 只用于纯解析/配置/序列化；一旦用于真实 DB/schema/CRUD，测试必须放 integration。历史平铺测试已迁移；不得继续向 `tests/` 根目录新增 `test_*.py`。

unit 不得涉及真实 DB file、schema、CRUD 或 store/runtime 协作：禁止使用 FastAPI `TestClient` / app lifespan、运行 Alembic migration、导入 `tests.integration.*` helper、验证真实 SQLite schema lifecycle / DB runtime orchestration、导入 `sqlite3` 后创建真实 DB file、调用生产 `_init_db()`、用 `DATABASE_URL=sqlite:///...` 指向持久路径。unit 只可覆盖：只读 legacy shim / public API / path constant 级别的代码逻辑。

### 何时跑什么

| 时机 | 命令 | 判据 |
|------|------|------|
| TDD 红/绿每步 | `uv run pytest <file>::<test> -x -q` | 见红/见绿 |
| 单 task 收尾 | 受影响层（unit 或 integration） | 该层无新增失败 |
| change / PR 收尾 | `make test-pr` + `uv run pytest tests/integration -q`（不带 `-x`，对照 main 基线） | test-pr 全绿；integration 无新增失败 |

覆盖门禁口径：push 路径仅看 unit，`make test-unit-ci` 的 `coverage report --fail-under=76`；每日定时路径看合并覆盖，`make test-coverage-ci` 的 `coverage report --fail-under=88`。

**门禁判据是「无新增失败」，不是零失败**：当前（2026-06）约有 2 unit + 19 integration 预先存在失败（`permission_gate` / agent-access 重构遗留，owner 非测试改动者）；其中 2 个 unit（`test_loop_permission_gate.py`，flaky）已在 `make test-pr` 用 `--deselect` quarantine。`make test-pr` 的 ruff 只扫本分支 changed-vs-main 的 `.py`——你只对自己改过的文件负责。

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

- **工具注册**：`tools/builtin_tools.py` 通过 import 副作用注册工具；`tools/__init__.py` 顶部 `from fleetent.tools import builtin_tools` 承载此副作用，`runtime/loop.py` 顶部 `import fleetent.tools` 触发注册，否则 `get_schemas()` 返回空
- **Skill 扫描**：`skills/registry.scan()` 在服务启动时运行（FastAPI lifespan）；CLI `run()` 每次调用时扫描
- **Context identity check**：`runtime/context.py` 的 `_keep_tail()` 使用 identity check（`m is tail[0]`），不用 `==`；patch/monkeypatch 目标须指 `fleetent.runtime.context`，patch 旧 shim `fleetent.context_mgr` 不生效
- **Runtime shim**：旧扁平路径（`agent_loop`/`context_mgr`/`agent_runtime`/`sub_agent`/`cancellation` 等 13 个）仅留 re-export shim；`monkeypatch.setattr` 须指真实子模块（如 `fleetent.runtime.loop`），patch shim 不生效
- **Session 原子写**：`session/manager.py` 写 `.json.tmp → rename`；测试中 monkeypatch `session_mgr.SESSIONS_DIR`
- **路径常量**：`DB_PATH`/`SESSIONS_DIR` 等在 import 时从 `paths.py` 求值一次；测试整体重定向用 `monkeypatch.setenv("FLEETENT_HOME", tmp_path)` + `importlib.reload()`，或 `monkeypatch.setattr(module, "<CONST>", ...)`
- **Bearer token 格式**：`Authorization: Bearer ma-<64hex>`（`ma-` 前缀区分服务 key 与模型 API key）
- **MCP 工具名**：`{server_id}__{tool_name}`（双下划线）
- **统一文件交换区 `/exchange`**（`artifact_exchange.py`）：MCP server 产物经 `/exchange/<server_id>/<rel>` 第二逻辑根寻址（与 `/workspace` 并列）。**归属轴 = workspace scope key（D0）**：`scope_key = workspace_scope_key(scope, session_id, agent_name)`（SESSION→session_id / AGENT→agent_name，与 `/workspace` 同源），`tenant_id`/`user_id` 不是文件隔离 key（前者 platform 概念、后者仅 memory/审批）。台账 `artifacts` 表 `scope_key` 列=访问/可见性，`session_id`/`user_id` 列=审计。发现两层：stdio 启动注入约定 cwd+XDG（`_stdio_params`）→ 咽喉 `_call_via_session` 结果路径确定性改写+登记（`rewrite_and_register`）→ 调用窗口 diff 兜底（`diff_register` + per-server `_call_window_lock`）。归属校验在 `resolve(path, scope_key, approved)` 一处：本 scope 放行 / 跨 scope 拒绝（唯一豁免=已过 permission gate 的 `approved`）。消费：`.views/<scope_key>/` 硬链接视图 ro 挂载为容器 `/exchange`（`exchange_mount` 能力，Docker=True；无能力后端走 `stage_file` staging 降级）。`send_file` callable risk（DM∧本scope∧交互→low，否则 medium 升级审批）；`send_im_message` 加 `files`（恒 medium，批准即跨 scope 授权）。`set_state_db`+`set_views_root` 在 `agent_app._init_agent_db_schema` 接线，未接线则台账休眠（register 抛 RuntimeError 被 best-effort 吞）
- **MCP 会话宿主**：每个 MCP 会话由 `_SessionHost`（`integrations/mcp/client.py`）的专属 task 持有，transport/ClientSession 的 enter/exit 同 task；`_active_sessions[(scope,id)]` 仍存 live `ClientSession` 供消费，`_session_hosts` 存宿主管生命周期。关停经 `aclose_all()`（接入 `agent_app._drain_and_close` 排干之后、`server.py` lifespan shutdown）。测试用 stub `_transport_cm` + `ClientSession`；**anyio 硬约束：cancel scope 必须同 task enter/exit**，不得用模块级 `AsyncExitStack` 持有连接（护栏强制）
- **model/resolver.py**：每次调用新建 client——故意的，client 无状态且廉价
- **Sandbox 可插拔后端**：`integrations/sandbox` 抽象为 `BaseSandboxBackend`（`backend.py`）+ `backends/docker.py`（默认）+ `backends/microsandbox.py`（本地 microVM，Apache-2.0，需宿主 KVM/HVF + 预装 runtime，否则 `is_installed()` 探测失败 → mode 降级 OFF）。后端经 `factory.create_backend` 按 `sandbox.backend`（agent.yaml > platform.yaml > 默认 docker）选型。能力差异经 `BackendCapabilities`（`persist_workspace`/`workspace_mount`/`orphan_cleanup`）门控，manager/cleanup 按能力降级、不用 isinstance。`client.py` 是 `SandboxClient = DockerBackend` 的 re-export shim——`monkeypatch`/`patch` Docker 内部（如 `_KILL_GRACE_SECONDS`、`_logger`）须打在 `backends.docker`，打 shim 不生效
