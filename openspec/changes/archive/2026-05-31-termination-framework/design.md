## Context

`agent_loop.py` 的 `run()`（行 127）与 `run_stream()`（行 244）均为 `while True`，唯一退出点是 `finish_reason != "tool_calls"`。没有步数上限、连续失败保护，也没有统一的终止原因记录。`log_run`（eval_logger）是现有的 trace 写入点。

本 change 是 v1.0「运行治理」的地基（roadmap 波次 1 / AR1）。后续 AR4 循环检测、AR2 预算与 Grace Call、AR19 取消传播都将作为新的终止 checker 接入同一框架。因此本次的首要目标是**把扩展缝设计对**，避免后续反复改主循环热点。

约束（CLAUDE.md）：禁止 AI 框架；禁止全局可变状态（阈值/配置必须可 monkeypatch 注入）；新模块结构为 import → 常量 → 数据类 → 函数；mypy strict；TDD Hard Gate。

## Goals / Non-Goals

**Goals:**
- 在 `run()` 与 `run_stream()` 引入单一终止检查点，行为一致。
- 提供 `TerminationController` + checker 注册表（策略模式），新增原因零侵入主循环。
- 接入 `max_turns`、`consecutive_failures`、`approval_rejected` 三个无需新增基础设施的原因。
- `max_turns` / `consecutive_failures` 阈值支持部署级配置（Settings env 字段）+ 调用参数覆盖。
- 终止原因码写入 trace。
- 为 `loop_detected` / `budget_exceeded` / `cancelled` 预留原因码与注册位。

**Non-Goals:**
- 不实现 loop_detected / budget / cancel 的判定逻辑（各自后续 change）。
- 不实现 Grace Call（AR2 范围）——本次终止即返回当前已有回复，不额外调用 LLM 生成总结。
- 不为 `run_stream()` 补齐审批拦截（现状流式路径不做审批，`approval_rejected` 仅在 `run()` 生效）。
- 不改动 model fallback、工具 dispatch、permission_gate 自身、上下文压缩的既有行为。

## Decisions

### D1：策略模式 + 注册表作为扩展缝
新增 `src/fleetent/termination.py`：
- `StopReason`：`str` 枚举。本次生效值 `normal` / `max_turns` / `consecutive_failures` / `approval_rejected`；预留（定义但本次不注册 checker）`loop_detected` / `budget_exceeded` / `cancelled`。
- `LoopState` 数据类：承载 checker 判定所需的可变运行态（`turn` 轮数、`consecutive_failures` 计数、`approval_rejected` 布尔标志），由主循环更新、传给 checker 只读评估。
- `TerminationChecker` 协议：`check(state: LoopState) -> StopReason | None`。
- `TerminationController`：持有有序 checker 列表，`should_stop(state) -> StopReason | None` 依次调用，返回首个非 None 原因；提供 `register(checker)`。
- 内置 `MaxTurnsChecker(max_turns)`、`ConsecutiveFailuresChecker(threshold)`、`ApprovalRejectedChecker()`（读 `state.approval_rejected` 标志）。

**为何**：后续 AR4/AR2/AR19 只需新建 checker 文件并 `register`，不碰主循环判定分支——满足 spec「新增原因零侵入」。
**Alternatives**：①在主循环里写 if/elif 链——被否，违背扩展缝目标，每加一个原因都改热点；②抛异常驱动终止——被否，终止是正常控制流而非异常，且难以携带结构化原因码。

### D2：阈值经 Settings 配置 + 调用参数覆盖（对齐 context_mgr 模式）
不引入 settings.yaml（项目实际无此文件，配置机制是 pydantic-settings 读 env）。沿用 `context_mgr._default_config()` 的成熟做法：
- `config.py` 的 `Settings` 增加 `agent_max_turns: int = 50`、`agent_max_consecutive_failures: int = 3`（env 可配，与 `context_max_tokens` / `permission_gate_*_timeout_seconds` 同类）。
- `termination.py` 提供 `_default_config()`：惰性 `from fleetent.config import Settings`（同 context_mgr 第 11 行），返回阈值 dict。
- `run()` / `run_stream()` 增加可选参数 `max_turns: int | None`、`max_consecutive_failures: int | None`。

解析优先级：**调用参数 > Settings（env）> pydantic 字段默认值**。测试通过传参或传 config 注入，不实例化真 `Settings`（避免 `anthropic_api_key` 必填）。
**为何**：项目既有运行旋钮（context 阈值、permission 超时）全部走 Settings env 字段；再引 YAML 既违背「无新依赖」原则也与现有代码割裂。Settings 字段默认值即单一事实来源，不再额外定义重复的模块常量。
**Alternatives**：①模块级 `DEFAULT_*` 常量——被否，与 Settings 默认值重复，且不可 env 配置；②settings.yaml——被否，文件不存在、机制不符。

### D3：连续失败的判定口径
工具调用结果若表征失败（dispatch 抛错被捕获、或返回带错误标识的结果），计 1 次失败；任一成功 dispatch 重置计数为 0。单轮多工具调用时，逐个累计/重置。**审批被拒不计入连续失败**——它走独立的 `approval_rejected` 终止路径（见 D6），不与 `consecutive_failures` 混淆。
**为何**：与 spec「成功调用重置计数」一致；口径简单、可单测；两种终止语义解耦，trace 原因码不歧义。
**Open**：dispatch 当前直接返回字符串结果、失败如何归一化（异常 vs 错误字符串）需在实现时确认——见 Open Questions。

### D4：终止检查点位置
在每轮 `while` 顶部、`maybe_compress` 之后、发起 LLM 调用之前调用 `controller.should_stop(state)`；返回非 None 则 break 并记录原因。`state.turn` 在每轮自增；`state.consecutive_failures` 在工具结果处理处更新。
**为何**：在 LLM 调用前判断可避免「已达上限还多打一次模型」；与 spec「终止判定优先于继续迭代」一致。

### D5：trace 写入
`StopReason` 经由 `log_run` 新增的 `stop_reason` 参数写入。正常结束记 `StopReason.normal`。
**为何**：复用现有唯一 trace 出口，改动最小。eval_logger 字段为追加式、向后兼容。

### D6：approval_rejected 改为终止而非继续循环
现状 `run()` 中审批被拒（`decision != "approved"`，行 167-168）将一条 `"tool execution {decision}: ..."` 字符串作为 tool_result 追加并**继续循环**，与 agent-runtime.md 场景 4「reject 后取消当次任务」矛盾。本次改为：审批被拒时置 `state.approval_rejected = True`，由 `ApprovalRejectedChecker` 在下一轮检查点终止；被拒工具不再产生「继续」语义的 tool_result（仍写入一条 tool_result 占位以保持消息契约完整，避免出现「有 tool_call 无 tool_result」的残缺序列）。
**为何**：纠正现状与文档冲突；复用已存在的 permission_gate 流程，无需新增基础设施，符合「本次只接入零基础设施依赖原因」边界。
**作用域**：`run_stream()` 当前不做审批拦截（行 309-316 直接 dispatch），故本次 `approval_rejected` 仅在 `run()` 生效——流式审批补齐是独立的既有缺口，不在本 change 范围。
**Alternatives**：把 `approval_rejected` 留作纯预留原因——被否，现状缺陷已与 spec 场景明确冲突，顺手修正成本低且边界清晰。

## Risks / Trade-offs

- [`run()` 与 `run_stream()` 是两份独立循环，可能行为漂移] → 终止判定逻辑全部收敛在 `TerminationController`，两处仅调用同一 API；用例覆盖两条路径。
- [`max_turns` 默认值过小会截断正常长任务] → 默认值取保守上限（50），可经 Settings env 或调用参数覆盖；trace 记录便于事后调参。
- [审批被拒改为终止可能影响依赖「拒绝后继续」隐含行为的调用方] → 经核查现状该路径仅追加错误字符串继续，无下游依赖；改为终止与场景 4 一致，并补占位 tool_result 保消息契约。
- [连续失败口径与现有 dispatch 错误表示不吻合] → 实现首步先核对 `dispatch` 失败返回形态，必要时在主循环侧做归一化，不改 dispatch 契约。
- [预留原因码被误认为已实现] → spec 明确「未注册 checker 的原因永不触发」；design Non-Goals 标注。

## Open Questions

- `dispatch` 失败的归一化形态（抛异常 / 返回带错误前缀的字符串）——实现第一步用现有 `tests/test_agent_loop.py` 与 `tool_registry` 核实后定，再决定 `ConsecutiveFailuresChecker` 的失败判据。
- `max_turns` 与 `max_consecutive_failures` 的默认值最终取值——本次给保守默认（50 / 3，经 Settings env 可配），后续可随 AR18 预算配置统一收口。
