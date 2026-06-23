## Why

reflection 是 agent 自我维护的核心闭环：读运行轨迹 → 生成 memory/skill 提案 → 经审批门 → apply 落地副作用（记忆置 stale / skill 写盘）。这条链路目前**只有单进程 unit/integration 覆盖**——没有一条 e2e 在真实多进程 managed 栈下证明"提案被生成、经真实 `/im/route` 审批、apply 真改了 agent 侧数据"。reflection 横跨 agent runtime（scheduler + 生成）、governance（reflection_gate）、im_gateway（normalizer 审批入口）、session/observability（轨迹素材），单进程 mock 永远测不到跨进程的真实接线（scheduler 是否真 fire、`set_state_db` 是否真接上、`/im/route` 审批是否真委派到 reflection_gate）。地基 harness（`e2e-managed-stack-coverage` / change A 的 `managed_stack`）已落地，正好解锁这条覆盖。

近期接线已就绪：skill-apply stub bug 已修（commit 12ed93b5，`reflection_gate.py` 现真调 `apply_skill_proposal_to_boundary`），low-risk auto-apply 已落地（commit 32ce06a5），proposal 路由已落地（commit 633980e3）。三处都缺端到端守门。

## What Changes

- 新增 e2e：在多进程 managed 栈下起一个 reflection-enabled agent（agent.yaml `reflection.enabled=True` + 极短 `interval_seconds`，scheduler 自然 fire），覆盖：
  - **memory-maintenance 提案 → 经真实 `/im/route` 本人 approve → apply**：断言 `reflection_proposals.status` 转 applied + 副作用（对应 memory item 置 stale）。
  - **low-risk auto-apply**：`reflection.auto_apply.allow_low_risk=True` 时，risk=low & action=mark_stale 的提案**无需审批直接 applied**，断言 `applied_at` 已落、无 pending approval。
  - **skill 提案 → approve → apply**：断言 SKILL.md 真写盘（`apply_skill_proposal` → `write_skill` + registry.reload）。
- 新增 helper `tests/e2e/_reflection_helpers.py`（**本 change 独占文件**）：seed reflection-enabled agent、注入可被反思的轨迹素材、经 `/im/route` 发审批命令、跨进程轮询 agent_state.db 与副作用。**不重构核心 `managed_stack`、不改 `conftest.py` 核心**。
- 进 slow/nightly lane（`make test-e2e`），**不**进 per-merge `make test-pr`。

> apply 第一组任务是**可行性探针**：multi-process 下 agent 是独立子进程，绝不能 in-process mock。须先实测 reflection 真实触发方式、素材造法、跨进程观测点。若探针判定某条 multi-process 不可不 mock 地跑通，design / tasks 诚实降级或标 deferred（见 design.md）。

## Capabilities

### New Capabilities
- `e2e-reflection-lifecycle`: 多进程 managed 栈下的 reflection 完整生命周期端到端覆盖——提案生成、经真实 `/im/route` 审批、memory-maintenance 与 skill 两类 apply、low-risk auto-apply。

### Modified Capabilities
（无；不改任何现有 capability 的 requirement，纯新增 e2e 覆盖。）

## Impact

纯测试侧改动，零 src 产品代码改动。

- **owning package**：`tests/e2e`（新增 test 文件 + `_reflection_helpers.py`）；复用 `tests/e2e/conftest.py::managed_stack` 与 `tests/e2e/_llm_stub.py` 既有基建
- **public API surface**：无（纯测试侧；不新增/改 src public API）
- **owned tables**：无（只读验证 agent 侧 `agent_state.db` 的 `reflection_proposals` / `approval_requests` 落盘 + skill 目录副作用）
- **config namespace**：无（仅在测试 seed 的 agent.yaml 里启用既有 `reflection` 配置块）
- **cross-module dependencies**：测试编排既有 platform/node/agent 三进程；触达 agent runtime（scheduler）、governance（reflection_gate）、im_gateway（`/im/route`/normalizer）、reflection（store/apply）的真实运行时接线，不引入 src 跨模块依赖
- **migration / shim**：无
- **受影响代码**：仅 `tests/e2e/`；核心 `managed_stack` fixture 与 `conftest.py` 核心**冻结不动**（新增逻辑放独占 `_reflection_helpers.py`，避免与并行波 B/C/D 撞 `conftest.py`）
- **CI**：进 `make test-e2e` slow/nightly lane，不进 per-merge 门禁
- **与 B（`e2e-im-inbound-approval`）边界**：B 测 `notify_user` fan-out **投递原语**；本 change 测 reflection 提案→审批→apply **全程**（审批走真实 `/im/route`，但不重复测 fan-out 原语本身）。两波不同 test 文件、不同 helper。
