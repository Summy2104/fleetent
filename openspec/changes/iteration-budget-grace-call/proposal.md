## Why

主循环（`agent_loop.run()` / `run_stream()`）目前只有 `max_turns`（执行步数）一个硬上限作为预算约束，且到达上限是**硬切断**——直接以 `max_turns` 终止，返回当时已有的内容。这带来两个问题：①预算维度太单一——长任务可能步数没超、但 token 用量或美元成本已经失控，平台无从拦截；②硬切断体验差——任务在最后一轮戛然而止，用户可能拿到一个半截、没有收束的回复，而不是「我做到这里、当前结论是 X」的总结。

这是 AR2（迭代预算与 Grace Call）。它把预算从单维扩展为**三维**（执行步数 / token 用量 / 美元成本），并在任一维度**将要**耗尽时不硬切断，而是给 AI **最后一次** LLM 调用（Grace Call）专门生成「当前进展总结」，再以 `budget_exceeded` 原因码（AR1 已预留）终止。AR1 终止框架（已合入 `termination.py`）提供「checker 注册即接入、不改循环体」的扩展点，本 change 为该原因码补 checker，并在终止收尾处插入 Grace Call。

> 本 change 是波次 3 的**接口地基**：预算的三个计量维度（步数 / token / 美元成本）接口会被 AR18（五层成本预算：单次任务 / session / 用户 / agent / 全局）与 MR2（成本感知路由）复用——它们在本 change 定义的维度与计量口径之上扩展层级与路由决策。因此本 change 需把「计量维度 + 用量累计」的接口定准并标注为契约（见 design D1）。

## What Changes

- 新增**预算计量与判定**（建议 `src/fleetent/budget.py`）：定义三维预算（`max_turns` / `max_tokens` / `max_cost_usd`）的配置载体、per-run 用量累计器（`BudgetUsage`），以及「任一维度将耗尽」的判定。
- 主循环每轮累计用量（步数 +1；token 取自每轮 LLM 响应 usage；美元成本由 token 用量 × 模型单价估算），并在下一轮 LLM 调用前判定预算。**注意**：`run()` 现状只在循环末取最后一次 `response.usage`、循环内不累计，本 change 须新增「每轮 LLM 调用返回后即累计进 `BudgetUsage`」的落点（见 design D1），否则预算判定滞后整任务、token/成本维度形同虚设。
- 预算判定实现为注册进 AR1 框架的 `BudgetChecker`，命中时返回 `budget_exceeded`，**不改循环体判定分支**。
- **Grace Call**：检测到预算将耗尽并触发 `budget_exceeded` 终止时，主循环不直接收尾，而是对 AI 追加一条「请用一段话总结当前进展与已得结论」的指令，发起**最后一次** LLM 调用，把其输出作为最终回复。
- **Grace Call 预算（决策已锁定）**：Grace Call 使用从主任务 token 预算按**固定比例预留**的独立 token 上限（默认比例 + 保底下限，见 design D3），经 pydantic `Settings` 暴露、可由 `.env` / `config/settings.yaml` 覆盖。Grace Call 自身失败（如超时/报错）则**返回已有的部分结果**，不再重试、不崩溃。
- **系统内部操作豁免**：上下文压缩等系统内部 LLM 调用产生的 token/成本**不计入**任务预算（仅计入「为完成用户任务而进行的主循环 LLM 调用」）。
- `budget_exceeded` 终止时原因码与触发它的维度写入 trace（复用 AR1 的 `stop_reason` 出口）。

## Capabilities

### New Capabilities
- `agent-iteration-budget`: 三维迭代预算（步数 / token / 美元成本）+ Grace Call。任一维度将耗尽时不硬切，给 AI 最后一次 LLM 调用生成「当前进展总结」，再以 `budget_exceeded` 终止；Grace Call 使用按固定比例预留的独立 token 预算，自身失败则返回已有部分结果；系统内部操作（如压缩）豁免计入。实现为注册进 AR1 终止框架的独立 checker，预算可配置。计量维度接口对外发布为 AR18 / MR2 依赖的契约。本 capability 同时新增一条「`budget_exceeded` 终止已接入主循环」需求：AR1 spec 把 `budget_exceeded` 列为「已定义但无 checker、永不触发」的预留原因码，本 change 注册 `BudgetChecker` 后该原因码成为可触发终止原因——该接入需求归本 change 自己的新 capability（ADDED），不通过 MODIFY `agent-loop-termination` 的「可扩展的终止策略注册表」需求实现，避免与并行 change（循环检测 / 取消传播）就同一条注册表需求互相覆盖。

### Modified Capabilities
- `agent-loop-termination`：仅 MODIFY 其 `max_turns` 终止需求——这是真实存在、单一归属的既有需求，其语义确被本 change 改变：`max_turns` 单维硬切断在「步数」维度的角色被本 change 的预算判定**取代**（步数维度并入三维预算、改走 Grace Call 收尾、命中产出 `budget_exceeded`）。**不** MODIFY 该 capability 的「可扩展的终止策略注册表 / 预留原因」需求（`budget_exceeded` 接入改由本 change 新 capability 的 ADDED 需求承载，见上）。

## Impact

- **代码**：
  - 新增 `src/fleetent/budget.py`（`BudgetConfig` 三维上限 + `BudgetUsage` per-run 累计器 + 美元成本估算 + 「将耗尽」判定 + `BudgetChecker`）。**计量维度接口对外契约**（见 design D1）。
  - 修改 `src/fleetent/termination.py`：`budget_exceeded` 原因码已存在；`LoopState` 承载或旁挂 `BudgetUsage` 引用（默认零用量，向后兼容）。
  - 修改 `src/fleetent/agent_loop.py`：`run()` / `run_stream()` 新增可选预算参数；`_build_controller` 注册 `BudgetChecker`；每轮累计 token/成本/步数；`budget_exceeded` 终止收尾处插入 Grace Call（最后一次 LLM 调用 + 失败降级为已有部分结果）；压缩等系统内部调用不计入。
  - 修改 `src/fleetent/config.py`：新增 Settings 字段（默认 token/成本上限、Grace Call 预留比例与保底下限——见 design D3）。
  - 可能需要模型单价映射（token → 美元）落点：在 `budget.py` 内置可注入的单价表（模块级不可变常量，可 monkeypatch），不引入云服务。
- **配置**：`config/settings.yaml.example` 增补预算相关字段示例（含 Grace Call 预留比例与保底下限）。
- **迁移项（可观察行为变更，必须显式处理）**：
  - **`stop_reason` 语义变更**：此前以 `stop_reason == "max_turns"` 终止的任务，本 change 后将以 `stop_reason == "budget_exceeded"`（`budget_dimension == "turns"`）终止。`StopReason.max_turns` 枚举成员**保留**（不删，兼容既有引用与历史 trace），但主循环**不再产出**它——步数维度命中由 `BudgetChecker` 统一产出 `budget_exceeded`（见 design D2）。任何依赖 `stop_reason == "max_turns"` 的下游统计/断言须迁移。
  - **收尾路径变更**：步数维度命中从「硬切断直接返回当时内容」改为「Grace Call 生成总结后返回」。
  - **既有 `max_turns` 单测迁移**：`tests/test_agent_loop.py` / `tests/test_termination.py` 中断言 `stop_reason == "max_turns"` 或硬切断收尾的用例，须迁移为断言 `budget_exceeded` + `budget_dimension == "turns"` + Grace Call 收尾路径（具体任务见 tasks）。
  - **`MaxTurnsChecker` 退役**：不再注册到 `_build_controller`（保留类定义与否见 design D2 / tasks）。
- **测试**：新增 `tests/test_budget.py`（三维判定、成本估算、Grace Call 预留计算）；`tests/test_agent_loop.py` 补充「预算将耗尽 → Grace Call 生成总结 → `budget_exceeded` 终止」「Grace Call 失败降级为部分结果」「压缩调用不计入预算」用例。LLM 调用按规范 mock（`patch get_async_client_and_config`）。
- **不影响**：model fallback、错误分类、permission_gate、`consecutive_failures` / `approval_rejected` 判定不变；不引入新依赖、不引入云服务。
  - 注意：步数维度的终止**确有可观察行为变更**（见上「迁移项」：`stop_reason` 由 `max_turns` 改为 `budget_exceeded`、收尾由硬切改为 Grace Call），不在「不影响」之列；不传预算参数时其余维度沿用部署默认。
