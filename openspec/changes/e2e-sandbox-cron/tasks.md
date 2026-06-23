## 1. 探针：定位真实 API 形状与观测点（先于断言，不写死假设）

- [ ] 1.1 **沙箱探针**：确认测试侧怎么调到后端 `available()`（`create_backend(...).available()` async / `SandboxManager` 可用性查询 / `docker version` 同步探针），选定 skip 判据写法；确认 managed 栈 seed 出的 agent 是否注册了 `run_code` 工具、是否需在测试侧 agent 定义显式开沙箱。记录结论。
- [ ] 1.2 **LLM stub 探针**：确认 `tests/e2e/_llm_stub.py` 是否已支持产出确定性 `run_code` tool-call；不支持则规划在 stub 内加确定性分支（仅测试侧）。记录结论。
- [ ] 1.3 **cron 探针**：定位 cron 任务的真实创建路径（admin API？agent `schedule` 工具？测试侧直写 `schedule_store`？）、触发方式（跨进程能否 `run_now` vs 极短 interval/once 自然 fire）、观测点（agent `agent_state.db` 的 `schedule_store` run-state 写回的物理路径 / 投递回复）。确认 managed 栈 seed 出的 agent 是否 `scheduling.enabled`。记录结论。**不写死假设**。

## 2. 沙箱 e2e：run_code 在 agent loop 中执行

- [ ] 2.1 **测试（红）**：新建 `tests/e2e/test_managed_stack_sandbox.py`，用 `managed_stack`：开头探 `available()`，假则 `pytest.skip`；真则向 agent 发一条触发 `run_code` 的指令，断言沙箱执行输出回折到 chat 最终回复。先跑见红（`uv run pytest tests/e2e/test_managed_stack_sandbox.py -x -q`）。
- [ ] 2.2 **实现（绿）**：补齐 stub 的 `run_code` tool-call 分支（如 task 1.2 需）、测试侧 agent 沙箱启用 / skip 判据接线，让测试在 Docker 可用时绿、不可用时 skip。跑同一最窄命令见绿。

## 3. cron e2e：任务创建并触发 agent

- [ ] 3.1 **测试（红）**：新建 `tests/e2e/test_managed_stack_cron.py` + 本 change 独占 `tests/e2e/_cron_helpers.py`（创建/触发/观测薄封装）。用 `managed_stack`（或 helper 包一层启用调度的 agent）：创建一个 scheduled task → 使其触发（按 task 1.3 探针结论：自然 fire 优先）→ 有界轮询观测 agent 跑通的结果（run-state 写回 / 投递回复）。先跑见红（`uv run pytest tests/e2e/test_managed_stack_cron.py -x -q`）。
- [ ] 3.2 **实现（绿）**：实现 `_cron_helpers.py` 的创建/触发/观测接缝，让测试过；若红是真链路问题（创建未生效/未 fire/未写回），定位是哪段——这正是 e2e 要抓的回归。跑同一最窄命令见绿。

## 4. 收尾 + lane + 边界自检

- [ ] 4.1 `make test-e2e` 跑这批（含 2 个新 test 文件 + `_cron_helpers.py`），确认沙箱在无 Docker 时 skip、有 Docker 时绿，cron 绿。
- [ ] 4.2 确认这批**不在** `make test-pr` 里（test-pr 不跑 `tests/e2e`）。
- [ ] 4.3 `make test-pr` 仍全绿（本 change 纯 test 侧、不碰 src，对照 main 基线无新增失败）。
- [ ] 4.4 **边界自检**：仅新增 `tests/e2e/test_managed_stack_sandbox.py`、`tests/e2e/test_managed_stack_cron.py`、`tests/e2e/_cron_helpers.py`（及 task 1.2 若需的 `_llm_stub.py` 测试侧 stub 分支）；**未改** `tests/e2e/conftest.py::managed_stack` 核心、**未改任何 src**。如确需改核心 fixture 或 src，停下说明（违反并行纪律 / 零 src 契约）。
