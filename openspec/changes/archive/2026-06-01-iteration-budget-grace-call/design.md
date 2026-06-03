## Context

`agent_loop.py` 当前唯一的预算约束是 `max_turns`：`_build_controller`（行 46-59）注册 `MaxTurnsChecker`，主循环检查点（行 290 / 487）命中即以 `max_turns` 硬切断（直接 `break`，返回当时 `msg.content`）。LLM 响应的 token 用量在 `run()` 里通过 `response.usage`（行 387）、在 `run_stream()` 里通过逐 chunk 累计 `total_prompt_tokens` / `total_completion_tokens`（行 525-527）已经拿得到，但仅用于 trace 记录，**未参与任何预算判定**。

AR1 终止框架（已合入 `termination.py`）把 `budget_exceeded` 列为预留 `StopReason`，并提供「注册 checker 即接入」扩展点。本 change 为该原因码补 checker，并把 `max_turns` 这个单维硬切断升级为「两维预算（步数 / token）+ Grace Call 优雅收尾」。

> review 后调整：原设计含第三个维度「美元成本」（内置单价表估算），并设想被波次 3 的 AR18 / MR2 复用。该维度已被**整体移除**——单价表维护成本高、负责人不需要；预算固定为步数 / token 两维。波次 3 的 MR2（成本感知路由）/ AR18（分层预算）将自行定义成本口径，**不再复用**本 change 的接口。下文涉及成本维度的 D5 及相关条目均已删除或改写。

Grace Call 预算的口径已由负责人锁定并记录在 `docs/capabilities/agent-runtime.md` 的「待决问题」中（该条已由 张洋 于 2026-05-31 标为「已决」）：Grace Call token = 主预算固定比例（默认 5%，保底 512 tokens），经 Settings 可覆盖；Grace Call 失败返回部分结果。本 change 的 D3 引用该文档决策落地，不另立无出处的结论。

约束（CLAUDE.md）：禁止 AI 框架；禁止 ORM；禁止全局可变状态（预算配置为可注入的模块级常量，用量累计挂在 per-run 对象上）；不吞异常（Grace Call 失败要 log 并降级，不静默崩溃）；新模块结构为 import → 常量 → 数据类 → 函数；mypy strict；行长 100；TDD Hard Gate；测试 mock LLM。

**与并行 change 的关系（归档顺序 / spec 协调）**：AR2（本 change）、AR4（循环检测）、AR19（取消传播）同属波次 2 Track A，都依赖 AR1 终止框架（`termination.py` 已合入），且都要把 AR1 spec 中各自对应的预留原因码（`budget_exceeded` / `loop_detected` / `cancelled`）从「已定义但永不触发」激活为「已接入可触发」。为避免三者 MODIFY `agent-loop-termination` 的同一条「可扩展的终止策略注册表」需求互相覆盖、归档顺序敏感，**本 change 不 MODIFY 该注册表需求**，而在自己的新 capability（`agent-iteration-budget`）里 ADD「`budget_exceeded` 终止已接入主循环」需求。AR1 spec 中「预留原因码尚未激活」的表述由本 change 起被本条 ADDED 需求超越；三个 change 各自独立 ADD、互不引用、无归档冲突，归档顺序可任意。**例外**：本 change 仍 MODIFY `agent-loop-termination` 的 `max_turns` 终止需求——这是真实存在、单一归属的既有需求，其语义确被本 change 改变（步数维度并入两维预算、改走 Grace Call 收尾），属正当 MODIFY（见 D2 与 spec 的迁移说明）。依赖上仅要求 AR1 已先行合入（已满足）。

## Goals / Non-Goals

**Goals:**
- 两维预算：执行步数 / token 用量，任一维度将耗尽即触发。
- 预算判定实现为注册进 AR1 的 `BudgetChecker`，命中返回 `budget_exceeded`，不改循环体。
- Grace Call：触发 `budget_exceeded` 时给 AI 最后一次 LLM 调用生成「当前进展总结」，作为最终回复。
- Grace Call 使用按固定比例预留的独立 token 预算（D3 锁定），可配置；自身失败降级为已有部分结果。
- 系统内部操作（压缩等）豁免计入预算。
- `budget_exceeded` 终止与触发维度写入 trace。

**Non-Goals:**
- 不做任何成本（美元）维度——review 后整体移除（见 Context 注）；波次 3 的 MR2 / AR18 自行定义成本口径，与本 change 脱钩。
- 不改 `consecutive_failures` / `approval_rejected` / 取消 / 循环检测判定。
- 不引入新依赖。

## Decisions

### D1：两维计量维度 + per-run 用量累计
新增 `src/fleetent/budget.py`：
- `BudgetConfig`（frozen dataclass）：`max_turns: int` / `max_tokens: int`，两维上限，任一可为「无上限」哨兵值。
- `BudgetUsage`：per-run 可变累计器，字段 `turns` / `tokens`，提供 `add(prompt_tokens, completion_tokens)` 累计（步数与 token 累加）。
- 「将耗尽」判定：任一维度 `usage >= config 上限` 即判定预算耗尽。
- `BudgetChecker(config, usage)`：实现 AR1 `TerminationChecker`，`check()` 在任一维度达上限时返回 `StopReason.budget_exceeded`。

**计量口径**：计量维度为 `{turns, tokens}` 两者；`BudgetUsage.add(...)` 是用量累计的唯一入口与口径（含「哪些调用计入、哪些豁免」的语义）。

**每轮用量累计的落点（代码现实修正）**：当前 `run()` 只在循环结束后取**最后一次** `response.usage`（agent_loop.py 行 387），循环内每轮**不累计**；只有 `run_stream()` 逐 chunk 累计 `total_prompt_tokens` / `total_completion_tokens`（行 525-527）。因此本 change 不能假设「usage 拿得到就能累计」——必须新增逐轮累计落点：
- `run()`：在每轮 `_call_with_fallback`（或等价 LLM 调用）**返回后立即** `usage.add(response.usage.prompt_tokens, response.usage.completion_tokens)`，把该轮 token/步数累计进 per-run `BudgetUsage`，而非沿用「循环末取最后一次 usage」。`BudgetChecker` 在下一轮检查点据累计后的 `BudgetUsage` 判定。
- `run_stream()`：复用现有逐 chunk 累计，但需在**每轮 LLM 调用结束时**把该轮增量结算进 `BudgetUsage`（而非仅在全流程末汇总），使 checker 能在轮间判定。

**为何**：把两维统一到一个累计器 + 一个判定，避免散落；frozen 配置 + 可变用量分离，符合「配置不可变、用量 per-run」。逐轮累计落点必须显式写明，否则沿用「循环末取一次 usage」会让预算判定永远滞后一整个任务，token 维度形同虚设。
**Alternatives**：用量累计放 `LoopState` 里——可旁挂引用，但累计逻辑独立成 `budget.py` 更内聚、可单测。

### D2：BudgetChecker 注册进 AR1，max_turns 维度并入（含 stop_reason 语义变更）
`_build_controller` 用 `BudgetChecker` 承载步数/token 两维；`MaxTurnsChecker` **退役**（不再注册），`max_turns` 作为 `BudgetConfig.max_turns` 维度并入两维预算，命中走 `budget_exceeded` + Grace Call 收尾（而非旧的 `max_turns` 硬切断）。

**`StopReason.max_turns` 枚举去留（明确选择：保留枚举值，但步数维度命中此后产出 `budget_exceeded`）**：
- `StopReason.max_turns` 枚举成员**保留**（不删，避免破坏既有引用与历史 trace 的可读性），但**主循环不再产出它**——步数维度达上限由 `BudgetChecker` 统一产出 `StopReason.budget_exceeded`（触发维度记为 `turns`，见 D6）。
- 这是一处**可观察行为变更**：此前以 `stop_reason == "max_turns"` 终止的任务，此后将以 `stop_reason == "budget_exceeded"` + `budget_dimension == "turns"` 终止，且收尾从硬切断改为 Grace Call。该语义变更在 proposal Impact 显式列为迁移项，既有 `max_turns` 单测须迁移到新收尾路径与新原因码（见 tasks）。

**为何**：步数本就是预算的一维；统一到 `budget_exceeded` 让「任一预算维度耗尽都走 Grace Call 优雅收尾」语义一致，避免「步数硬切、token 软切」的不一致体验。保留枚举成员而改由 budget 维度产出，兼顾「不破坏既有引用」与「收尾语义统一」。这要求 MODIFY `agent-loop-termination` 的 `max_turns` 终止需求（见 spec）。
**Alternatives**：①删除 `StopReason.max_turns` 枚举——被否，会破坏既有代码引用与历史 trace 解读；②保留 `MaxTurnsChecker` 独立硬切断、只为 token 加 checker——被否，会出现两种收尾路径（步数硬切 vs 预算 Grace Call），体验与 trace 口径不一致，违反 agent-runtime.md「任意预算维度耗尽时优雅停止」。

### D3：Grace Call 预算 = 按固定比例预留（引用 agent-runtime.md 已决条目）
本节落地 `docs/capabilities/agent-runtime.md`「待决问题」中已由 张洋（2026-05-31）标为「已决」的决策——Grace Call token = 主预算固定比例（默认 5%，保底 512 tokens），经 Settings 可覆盖，Grace Call 失败返回部分结果：
- Grace Call 的 token 上限 = 从主任务 token 预算（`BudgetConfig.max_tokens`）按**固定比例预留**，默认比例 **5%**；并设**保底下限**默认 **512 tokens**（即 `grace_max_tokens = max(round(max_tokens * grace_ratio), grace_floor_tokens)`），避免主预算很小时预留为 0 导致 Grace Call 无法生成有效总结。
- 比例 `agent_grace_call_token_ratio`（默认 0.05）与保底下限 `agent_grace_call_min_tokens`（默认 512）经 pydantic `Settings` 暴露，可由 `.env` / `config/settings.yaml` **覆盖**。
- Grace Call 是一次额外的 LLM 调用，使用预留 token 作其 `max_tokens` 上限，追加指令「请用一段话总结当前进展与已得结论，不要再调用工具」。
- Grace Call **自身失败**（超时 / 报错 / 返回空）→ **返回已有的部分结果**（主循环到终止前累积的最后一段 assistant 文本），记录降级，不重试、不崩溃。

**为何**：固定比例预留实现简单、可预测，且与主预算解耦——主预算耗尽后仍有一小块专款保证「能说一句总结」；保底下限防止小预算下预留为 0；失败降级保证用户至少拿到部分结果（满足 agent-runtime.md「失败则返回已有的部分结果」）。5% / 512 是保守默认，可配置上调。
**Alternatives**：①Grace Call 用完全独立的固定 token 配额（与主预算无关）——被否，负责人锁定为「按主预算比例预留」；②不给 Grace Call 单独预算、直接复用剩余——被否，预算已耗尽时剩余可能为 0，Grace Call 无空间。

### D4：系统内部操作豁免计入预算（当前架构下默认成立）
只有「为推进用户任务而发起的主循环 LLM 调用」计入 `BudgetUsage`。

**豁免的真实含义（澄清）**：本 change 的累计唯一入口是 D1 定义的「在主循环每轮 LLM 调用返回后显式 `usage.add(...)`」。压缩调用（`context_mgr.maybe_compress` 内部的摘要 LLM 调用）的 token **本就不流经** `BudgetUsage`——它在 `context_mgr` 内部消耗，主循环既不为它调用 `usage.add(...)`、其 usage 也不进入主循环的 `response.usage` 累计路径。因此在当前架构下「压缩豁免」是**默认成立**的：无需主动识别并排除压缩调用，只要不把压缩的 token 接进 `BudgetUsage.add` 即可。仅当未来压缩也上报 usage 并被接入累计时，才需要显式排除——本 change 不引入该路径，故按「默认不计入、无需主动排除」表述与实现。
Grace Call 本身使用其预留配额，不二次计入主 `BudgetUsage`；总之不让系统开销吃掉用户任务预算。

**为何**：agent-runtime.md 明确「系统内部操作（如压缩调用）可豁免计入预算」；当前架构下压缩 token 天然不流经累计入口，豁免默认成立，避免引入「主动排除压缩」的脆弱判定。
**Alternatives**：①把压缩 token 也接进 `BudgetUsage` 再主动排除——被否，无谓增加耦合与误差；②全部计入——被否，违反 agent-runtime.md 且惩罚正常的上下文管理。

### D5：(review 后移除：成本维度已拆)
原 D5 定义美元成本估算用的内置静态单价表（`MODEL_PRICING` / `DEFAULT_PRICING`）与表外模型保守默认口径。负责人 review 后**整体移除成本维度**：单价表维护成本高、负责人不需要该维度。`budget.py` 不再含任何单价表或成本换算，`BudgetUsage.add(prompt_tokens, completion_tokens)` 仅累计步数与 token。波次 3 的 MR2 / AR18 将自行定义成本口径，与本 change 脱钩。

### D6：trace 写入 budget_exceeded 与触发维度
`budget_exceeded` 终止时 `stop_reason = StopReason.budget_exceeded`，并把触发它的维度（turns / tokens 中哪个先到上限）随 trace 记录，经现有 `log_run` 出口写入（必要时新增一个 `budget_dimension: str | None = None` 可选字段，默认 None 向后兼容）。

**为何**：与 AR1 其它终止原因写 trace 一致；记录触发维度便于统计「任务多因步数 / token 哪类超限」。

### D7：run_stream 的 Grace Call 流式收尾结构（现状缺口补全）
**代码现实**：`run_stream()` 现在在检查点命中即 `break`，随后直接走 `log_run` 收尾（agent_loop.py 行 589）——没有「`break` 后再发一次流式 LLM 调用、把总结以 `text_delta` 流给客户端」的结构。`run()` 的 Grace Call 是一次普通（非流式）LLM 调用，但 `run_stream()` 必须把 Grace Call 也做成流式，否则用户在流式通道里拿不到总结增量。

**流式 Grace Call 结构**：`budget_exceeded` 在检查点命中 → 不直接 `log_run` 收尾，而是：
1. 追加 Grace Call 指令消息（「请用一段话总结当前进展与已得结论，不要再调用工具」）；
2. 以预留 `grace_max_tokens` 为上限**再发起一次流式 LLM 调用**，逐 chunk `yield` `text_delta` 把总结增量流给客户端；
3. 流结束后正常 `yield` `done` 并 `log_run(stop_reason=budget_exceeded, budget_dimension=...)`。

**Grace Call 自身失败 / 已 yield 部分事件后的降级**：
- 若 Grace Call 流式调用在**尚未 yield 任何 `text_delta`** 时失败 → 降级为「返回终止前已累积的最后一段 assistant 文本」：把该文本作为一次（或若干次）`text_delta` 补发后 `done`，记录降级，不重试、不崩溃。
- 若 Grace Call 已 yield 了**部分** `text_delta` 后中途失败 → 不回滚已流出的增量（客户端已收到），以已流出的部分内容收尾、`yield done` 并记录降级；不再重试、不抛未处理异常。
- 两种情形都保证：客户端最终都收到 `done`，不泄漏半截工具循环、不悬挂流。

**为何**：流式通道下「优雅收尾」必须是流式的总结，否则用户体验回退到「半截 + 无总结」；明确「已 yield 部分后失败不回滚」是因为流式增量无法收回，只能以已发内容收尾。
**Alternatives**：①`run_stream` 的 Grace Call 用非流式调用、整段一次性 yield——可行但与 `run_stream` 的逐增量语义不一致、失去流式体验；②命中即 `break` 不做流式总结（现状）——被否，正是本 change 要补的缺口。

## Risks / Trade-offs

- [Grace Call 预留比例过小导致总结被截断] → 设保底下限（默认 512 tokens）兜底；比例与下限均可配置上调；Grace Call 指令明确「一段话总结」控制长度。
- [`max_turns` 收尾从硬切改为 Grace Call 会改变现有 `max_turns` 用例的可观察行为] → MODIFY `agent-loop-termination` 的 `max_turns` 需求明确新行为（步数维度命中走 Grace Call）；更新 `tests/test_agent_loop.py` 既有 `max_turns` 用例为新收尾路径；Grace Call 失败时降级为部分结果，保证不返回空（除非本就无任何内容）。
- [Grace Call 额外一次 LLM 调用增加少量延迟] → 仅在预算耗尽终止时发生一次，使用受限的预留 token；换取「不给用户半截回复」的体验，符合 agent-runtime.md 验收场景 7/11。
- [`run_stream()` 的 Grace Call 流式语义与失败降级] → 见 D7：Grace Call 做成流式（`text_delta` 流出总结后 `done`）；尚未 yield 即失败则补发已有部分文本，已 yield 部分后失败则以已流出内容收尾——两种情形都保证 `done`、不泄漏半截工具循环、不悬挂流。
- [`run()` 现状无逐轮 usage 累计，token 维度可能滞后] → 见 D1：本 change 新增「每轮 LLM 调用返回后即 `usage.add(...)`」落点，不沿用「循环末取一次 usage」，使 `BudgetChecker` 能在轮间据累计用量判定。

## Open Questions

- （无）Grace Call 用量不二次计入主预算已在 D4/D6 定口径；`budget_dimension` 经 `log_run` 向后兼容末位 kw 参数写入已在 D6 定。逐轮累计落点与 run_stream 流式 Grace Call 结构已在 D1/D7 定死。成本维度已 review 后整体移除（见 Context 注 / D5）。
