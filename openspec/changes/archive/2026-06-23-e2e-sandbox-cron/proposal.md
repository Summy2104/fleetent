## Why

两条平台核心能力至今**没有任何多进程 managed 栈 e2e 守门**：

1. **沙箱在 agent loop 中执行**：agent 经 `run_code` 工具 → `SandboxManager.acquire()` → `backend.exec()` 跑代码并把输出折回对话。这是 agent 真正"会动手"的能力，单进程 unit/integration 之外，从没在真实多进程栈下端到端证明过"agent 收到指令 → 沙箱跑代码 → 输出回到 chat"。
2. **cron 调度触发 agent**：agent 进程内的 `CronScheduler`（APScheduler）按时 `_fire()` 构造消息 → 跑 agent → 投递回复（同 chat ingress 的 `_agent_run()`）。调度链同样只有单进程覆盖，没有 e2e 证明"任务被创建 → 触发 → agent 跑通 → 回复可观测"。

地基 harness（`tests/e2e/conftest.py::managed_stack` + `tests/e2e/_llm_stub.py`）已落地，正好解锁这两条端到端覆盖。两条路径相互独立，合一个 change 是因为它们共享同一个起栈基建、同属"补 managed 栈 e2e 覆盖"主线。

## What Changes

- 新增 e2e **沙箱路径**：在多进程 managed 栈下，让 agent 经对话触发 `run_code` → 断言沙箱执行的输出端到端回到 chat。**Docker 不可用时优雅 skip**（沙箱是 optional feature，后端 `available()` 探测失败即降级 OFF，不可硬失败）。
- 新增 e2e **cron 路径**：在多进程 managed 栈下创建一个 scheduled task 并触发 → 断言 agent 跑通、回复/run-state 可观测。
- 新增 e2e 专属 helper `tests/e2e/_cron_helpers.py`（cron 任务创建/触发/观测的薄封装），**不重构核心 `managed_stack`**。
- 进 slow lane（`make test-e2e`），**不**进 per-merge `make test-pr`。

## Capabilities

### New Capabilities
- `e2e-sandbox-cron`: 多进程 managed 栈下的两条端到端覆盖——① 沙箱 `run_code` 在 agent loop 中执行并把输出回折到 chat（Docker 不可用时 skip）；② cron 任务创建→触发→agent 跑通→回复可观测。

### Modified Capabilities
（无；不改任何现有 capability 的 requirement，纯新增 e2e 覆盖。）

## Impact

纯测试侧改动，零 src 产品代码改动。

- **owning package**：`tests/e2e`（新增 test 文件 + `_cron_helpers.py`）；复用 `tests/e2e/conftest.py::managed_stack`、`tests/e2e/_llm_stub.py`、`tests/integration/_migration_template` 既有基建
- **public API surface**：无（纯测试侧；不新增/改任何 src public API）
- **owned tables**：无（测试用隔离临时库；只读观测 agent 侧 `schedule_store` / 沙箱输出）
- **config namespace**：无
- **cross-module dependencies**：测试编排既有 platform/node/agent 三进程 + 沙箱后端（`integrations/sandbox`）+ agent 进程内 `cron_scheduler`；**不引入任何 src 跨模块依赖**
- **migration / shim**：无（复用 `apply_migrations`）
- **受影响代码**：仅 `tests/e2e/`；核心 `managed_stack` fixture **冻结不动**（新 helper 全部放本 change 独占的 `tests/e2e/_cron_helpers.py`，避免与并行 e2e 波撞 `conftest.py`）
- **CI**：进 `make test-e2e` slow lane，**不**进 per-merge 门禁
