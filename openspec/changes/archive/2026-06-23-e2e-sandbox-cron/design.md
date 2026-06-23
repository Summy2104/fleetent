## Context

地基 harness（`e2e-managed-stack-coverage`）已落地：`tests/e2e/conftest.py::managed_stack` 起单 tenant 单 agent 的真实多进程栈（platform + node + agent 三进程），`tests/e2e/_llm_stub.py` 提供确定性 LLM。本 change 在其上补两条独立的端到端覆盖，纯测试侧、零 src 改动。

已核实的真实代码路径（给 spec/tasks 用，apply 仍须用探针复核 API 形状）：

- **沙箱**：agent loop 经 `tools/builtin_tools.py:573` 的 `run_code()` 工具 → `SandboxManager.acquire()` → `backend.exec()`。后端选型 `integrations/sandbox/factory.py:create_backend`（agent.yaml > platform.yaml > docker 默认）。Docker 可用性探测 `backends/docker.py:54 available()`：`docker version` 探针失败 / daemon 不可达 → 返回 False，平台降级 OFF（不崩）。`DockerBackend.capabilities` 含 `workspace_mount`/`exchange_mount`。
- **cron**：调度器是 **agent 进程内**的 `CronScheduler`（`cron_scheduler.py:321`，APScheduler `AsyncIOScheduler`），在 **agent boot** 时由 `runtime/agent_app.py:_start_scheduler`（约 415 行）启动，条件 `agent.scheduling.enabled`。`_fire()`（161 行）构造消息 → `_agent_run()` 跑 agent → `_deliver()` 投递回复，并经 `_record_run()` 把 last_run_at/last_status 写回。手动触发用 `CronScheduler.run_now(task_id)`（503 行）。
- **schedule 持久化**：`schedule_store.py` 是 **agent-owned store**，落 per-agent `agent_state.db`（embedded migration v27），经 `set_state_db(db)` 在 agent boot 注入。**不是 platform 管理库**。任务创建可经 agent 的 `schedule` builtin 工具（`builtin_tools.py:706`，经对话）或直接 `schedule_store.create(...)` / `cron_scheduler.create_task(...)`。

## Goals / Non-Goals

**Goals**：① 端到端证明沙箱在 agent loop 中真执行并把输出回折 chat；② 端到端证明 cron 任务创建→触发→agent 跑通→结果可观测。两条都复用既有 `managed_stack`、零 src 改动、进 slow lane。

**Non-Goals**：不测沙箱的资源/网络隔离细节（unit/integration 已覆盖）；不测 cron 的时区/misfire 语义；不重构核心 `managed_stack`；不新增 src 产品代码或 API。

## ⚠️ 关键可行性风险（apply 第一步必须先验，不得写死假设）

### 风险 1 — Docker 在 CI/e2e 环境是否可用（沙箱 e2e 的成败前提）

沙箱是 optional feature。e2e 环境很可能**没有 Docker CLI 或 daemon 不可达**。沙箱 e2e **必须**在执行前探测后端 `available()`，不可用则 `pytest.skip`——绝不能硬失败。

- apply task 1 必须先确认：从测试侧怎么调到后端 `available()`（`create_backend(...).available()` 是 async；或 `SandboxManager` 暴露的可用性查询），以及 managed agent 实际选了哪个后端（默认 docker）。
- 还须确认：managed 栈下 agent 的 `run_code` 默认能力是否需要 agent.yaml 显式开启沙箱 / 注册 `run_code` 工具——若默认未注册到该 stub agent，e2e 需在 seed 时补齐（仅测试侧 agent 定义，不改 src）。
- skip 判据要稳：探测 async `available()` 用 `anyio`/`asyncio.run` 或同步探针（`docker version` 子进程返回码）任一可行方案，apply 选定后写进 helper。

### 风险 2 — cron 任务怎么创建、怎么触发、结果在哪观测

调度器在 **agent 进程**、store 在 **agent 的 `agent_state.db`**——不是 platform 库。task brief 里"经 admin API 建任务"的假设**需复核**：很可能没有平台 admin API 直建 cron 任务，而是经 agent 的 `schedule` 工具（对话内）或直写 agent 侧 `schedule_store`。apply task 1 必须先定位：

- **创建路径**：是否有 HTTP/admin API？还是只能经对话让 agent 调 `schedule` 工具？还是测试侧直接 `schedule_store.create(...)`（需先 `set_state_db` 接到 agent 的库）？managed 栈下 agent 是独立进程，测试进程**直写 agent_state.db 不一定指向同一文件**——须确认 agent 进程的 `agent_state.db` 物理路径，测试侧只读观测该文件。
- **触发路径**：手动 `run_now(task_id)`（但 scheduler 实例在 agent 进程内，跨进程不可直调）vs 用极短 interval/once 任务等其自然 fire（更贴近 e2e 真实链路，推荐）。apply 据探针定。
- **观测点**：`schedule_store` run-state 列（last_run_at/last_status，跨进程只读该 db 文件可见）和/或投递回复（需 connector，managed 栈下投递目标怎么观测）。优先选跨进程可观测且最简单的那个。

### 风险 3 — managed 栈下 agent 进程是否真启动了 scheduler

`CronScheduler` 仅在 `agent.scheduling.enabled` 为真时由 `agent_app._start_scheduler` 启动。`conftest.py` 的 `_seed_managed_agent` 默认 agent 定义**未必**开了 `scheduling.enabled`。apply task 1 必须确认 seed 出的 agent 是否启用调度；若未启用，e2e 需在测试侧 agent 定义补开（不改 `_seed_managed_agent` 核心，必要时本 change helper 起独立 seed 或新增 fixture 包一层）。

## Decisions

- **新 helper 进 `tests/e2e/_cron_helpers.py`（本 change 独占文件），不改 `managed_stack`**：避免与并行 e2e 波撞 `conftest.py`。沙箱 e2e 直接复用 `managed_stack`；cron e2e 所需的"启用调度的 agent" 若 `managed_stack` 默认 agent 不带，则在 helper 里包一层或用独立 seed，仍不动核心 fixture。
- **沙箱 e2e 先探后用**：测试开头探 `available()`，假则 `pytest.skip`；真则发指令触发 `run_code`，断言执行输出回折 chat。LLM stub 须能产出一条确定性的 `run_code` tool-call（确认 `_llm_stub.py` 是否已支持 tool-call，不支持则在 stub 加确定性分支——仍属测试侧）。
- **cron 触发走自然 fire 优先**：跨进程无法直调 agent 进程内的 `run_now`，故优先用极短 interval / 近未来 once 任务，让 agent 进程内 scheduler 自然 fire；观测点优先选跨进程只读可见的 `schedule_store` run-state 写回。apply 探针确认后定稿。
- **两条 e2e 各自独立测试文件**：沙箱、cron 互不依赖，分文件便于单独 skip / 定位。

## Risks / Trade-offs

- Docker 不可用 → 沙箱 e2e skip（已设计为优雅 skip，非失败）；这意味着无 Docker 的 CI 上该条不提供守门——可接受，slow lane 在有 Docker 的环境跑。
- cron 自然 fire 引入等待时间 → e2e 在 slow lane，用极短 interval + 有界轮询观测，可接受。
- 创建/触发/观测三个接缝的真实形状不确定 → 全部由 apply task 1 探针消解，spec/tasks 不写死。
