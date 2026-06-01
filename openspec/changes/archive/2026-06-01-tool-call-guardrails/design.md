## Context

AR4（`src/fleetent/loop_detector.py`）已落地主循环层**粗粒度**循环检测：

- 注册为 `TerminationChecker`（`agent_loop._build_controller` 行 168-169），在一轮所有工具 dispatch **之后**、下一次 LLM 调用前被 `should_stop` 评估。
- 数据源是 `LoopState.tool_history`（`termination.py`）——每次工具调用后由 `state.record_tool_call(...)` 追加 `(tool_name, arg_fingerprint, result_digest, success)`，并 FIFO 截断到 `window` 条。
- 判定走**窗口 Counter**：信号 A 统计窗口内 `(tool, arg_fingerprint)` 出现次数 ≥ `repeat_threshold`（`agent_loop_repeat_threshold`，默认 3）；信号 B 统计同工具成功结果 digest 停滞。
- 响应**两阶段**（`LoopDetectionChecker.check`）：首次命中设 `state.loop_warning_requested=True` 返回 None（主循环 `_maybe_inject_loop_warning` 注入纠正文本，置 `loop_warning_injected=True`）；已警告后再命中返回 `StopReason.loop_detected` 强制停止。
- 参数指纹由 `loop_detector.arg_fingerprint(arguments, ignore_keys)` 规范化（JSON parse → sort_keys → serialize → sha256），非 JSON 回退原串哈希，`ignore_keys` 为可选逃生舱。

`docs/capabilities/agent-runtime.md` 行 147-149 把 AR10 工具调用守卫定义为更**细粒度**的能力：「相同工具 + 相同参数**连续**重复 N 次 → 注入警告；忽略仍重复 → 停止」。行 277（Q3）悬空 N 默认值与可配置性。

doc 行 149「同一工具**连续失败** M 次 → 同等处理」**不归本 change**：连续失败终止**已由 AR1 `ConsecutiveFailuresChecker`（`agent_max_consecutive_failures=3`，任意工具连续失败 ≥3 → 停）覆盖**。失败只有执行后才知，「连续失败」天然是调用后检测，与 AR10「调用前边界」身份矛盾；3 次同工具连续失败时 AR1 同样到 3 会先停，AR10 再设同工具失败计数器是重复。故 AR10 **收窄为仅 N-重复守卫**；如需「失败先警告后停」属 AR1 `consecutive_failures` 策略增强，不在本 change（见 Non-Goals）。

约束（CLAUDE.md）：无 AI 框架；无 ORM（守卫为内存态计数，无持久化需求，若需查询用标准库 sqlite3，但本能力不引库）；无全局可变状态（N/M 阈值可注入、可配，计数器随 `LoopState` 生命周期，per-run 隔离）；新模块 import → 常量 → 数据类 → 函数；mypy strict 全注解；行长 100；TDD Hard Gate；测试 mock LLM、隔离 tmp_path。

## Goals / Non-Goals

**Goals:**
- 定义 dispatch **调用前边界**的细粒度守卫：检测「相同工具 + 相同参数**严格连续**重复」。
- 复用 AR4 `arg_fingerprint`（含 `ignore_arg_keys`）做参数比较，不重造；复用 `StopReason.loop_detected`。
- 钉死 AR10 与 AR4 的分工：AR4 = 窗口计数 / 调用后 / 终止 checker；AR10 = 严格连续计数 / 调用前 / dispatch 边界守卫。
- **解决 Q3**：给出 N（与 M）的默认值与可配置结论，不留 OQ。

**Non-Goals:**
- 不改 AR4 `loop_detector` 的窗口检测语义（仅复用其 `arg_fingerprint` 纯函数）。
- **不含「连续失败」守卫**：连续失败终止已由 AR1 `ConsecutiveFailuresChecker` 覆盖（见 Context）；本 change 不设同工具失败计数器、不新增失败阈值字段。「失败先警告后停」属 AR1 增强，不在此。
- 不改既有 checker 注册顺序（budget / consecutive_failures / approval / loop）。
- 不实现工具超时（AR 超时保护）、参数消毒、Secret 过滤——各属独立功能点。
- 不引入持久化（守卫计数为 per-run 内存态，随 `LoopState` 消亡）；不引入新依赖。

## Decisions

### D1（解决 Q3）：N 默认值与可配置性

**结论（解决 Q3）：**

- **① N 默认值 = 3**。「相同工具 + 相同参数严格连续重复」达到 3 次触发守卫。取 3 与 AR4 `agent_loop_repeat_threshold`（默认 3）**对齐**：两套检测对「重复几次算异常」用同一直觉阈值，避免运维心智里出现两个互相矛盾的「重复次数」。3 也避开误杀——连续 2 次相同调用在分页 / 轮询 / 重试场景里属正常，第 3 次背靠背完全相同才足以判定卡死。
- **② 可配置 = 是**。N 经两层覆盖（与 AR4 `_resolve_loop_config`、AR1 `resolve_limits` 同一「按次入参 > Settings > 默认」范式）：
  - `config.Settings.guardrail_repeat_threshold: int = 3`（部署级，env / settings.yaml 可覆盖）。
  - `run()` / `run_stream()` / 守卫构造函数的按次注入参数 `guardrail_repeat_threshold: int | None = None`（None 回退 Settings）。
  - **无全局可变状态**：阈值不是模块级可变量，而是经构造注入到守卫对象；默认值是函数签名 / Settings 字段的单一事实来源，测试用注入小阈值隔离。
- **不含连续失败阈值 M**：连续失败终止已由 AR1 `ConsecutiveFailuresChecker`（`agent_max_consecutive_failures=3`）覆盖，本 change 不引入 `guardrail_consecutive_failure_threshold` 字段（见 Context / Non-Goals）。Q3 仅就 N 给出决策。

**为何对齐而非另取值**：AR4 与 AR10 都回答「重复多少次算异常」，给同一默认值让运维只需理解一个数；二者差异在**计数方式**（窗口 vs 严格连续）而非阈值大小。可配置满足不同 agent 容忍度（数据分析 agent 可能合法地多次重试同一查询，可调高）。

**Alternatives**：①N 默认 2——被否，连续 2 次相同在分页 / 重试中常见，误杀率高。②N 不可配置写死——被否，违反「无全局可变状态 / 阈值可注入」硬规则，且不同 agent 容忍度不同。③N 与 AR4 阈值各自独立取值——被否，徒增运维心智负担且无场景需要二者不同。

### D2：守卫是 dispatch **调用前**边界检查，不是 AR4 那样的调用后 checker

AR4 在一轮工具**全部执行后**经 `TerminationController.should_stop` 读历史判定。AR10 在 `dispatch` **即将执行某工具调用前**判定：当「本次 `(tool_name, arg_fingerprint)` 与紧邻上一次相同」的**连续**次数达 N，即在执行该次调用前拦截，分两阶段：

- **Stage 1（第 N 次连续、尚未警告）→ 短路本次调用**：**不执行**这次工具调用（短路，省掉冗余执行——这是 AR10 相对 AR4 的核心价值）；为这个被跳过的 tool_call **补一条占位 tool_result**，其 content **就是纠正反馈**（复用 `_LOOP_WARNING_TEXT` 或守卫定制文案，如「已跳过：相同工具相同参数连续 N 次，请换思路」）。**一条 tool_result 同时满足两件事**：① 消息序列合法（有 tool_call 必有对应 tool_result，与 termination-framework 给 `approval_rejected` 补占位同一不变式）；② 给 LLM 反馈（让其下轮换思路）。同时**置共享 `loop_warning_injected` 幂等标志**——仅为与 AR4 协调（避免 AR4 在轮间再注入第二条警告），AR10 自身不依赖该标志驱动后续行为。
- **Stage 2（已警告、又来一次相同）→ 强制停止**：返回 `StopReason.loop_detected`。

**明确：AR10 不走 AR4 的 `_maybe_inject_loop_warning`（轮间注入独立警告消息）通路**——AR10 是 per-call，警告由这次短路的占位 tool_result 承载，不叠加轮间消息。

**为何**：①「严格连续重复」是比窗口重复更早、更确定的卡死信号，短路省掉一次无效工具执行的副作用与成本——这正是 AR10 相对 AR4 的核心增值。②dispatch 边界是工具调用的唯一收口（`tools.md`：`dispatch` 是工具执行收口），在此加守卫天然「细粒度到每次调用」。③与 AR4 互补而非重叠：AR4 兜底「窗口内分散重复」，AR10 精确拦「背靠背重复」。④占位 tool_result 复用 termination-framework 给 `approval_rejected` 补占位的同一不变式，消息序列始终合法。

**Trade-off**：守卫需在 dispatch 前拿到「上一次调用指纹」。复用 `LoopState`（per-run）承载连续计数即可，无需新存储；守卫与 AR4 共享同一 `LoopState`，但读写不同字段（AR4 用 `tool_history` 窗口，AR10 用新增的「连续计数」轻量字段），互不干扰。

### D3：复用 AR4 `arg_fingerprint` 与 `loop_detected`；首次命中机制 = 短路 + 占位 tool_result（兼警告），不走 AR4 轮间注入

- **参数比较**：守卫直接调用 `loop_detector.arg_fingerprint(arguments, ignore_arg_keys)`，与 AR4 同一份规范化逻辑（JSON sort_keys 哈希 + `ignore_arg_keys` 逃生舱 + 非 JSON 回退）。「相同参数」的判定标准在两套检测里**完全一致**，不出现「AR4 认为相同 / AR10 认为不同」的语义漂移。
- **终止词汇**：守卫强制停止时返回 `StopReason.loop_detected`（已有的预留枚举，trace 消费者已知词汇），不新增枚举。
- **首次命中机制（Stage 1）= 短路 + 占位 tool_result**：守卫**不执行**本次工具调用，为被跳过的 tool_call 补一条占位 tool_result，content 即纠正反馈（复用 `_LOOP_WARNING_TEXT` 或守卫定制文案）。该占位 tool_result 同时承载「消息序列合法」与「给 LLM 警告」两职。同时置共享 `loop_warning_injected` 幂等标志，**仅为与 AR4 协调**（避免 AR4 再注入第二条轮间警告）。
- **不走 `_maybe_inject_loop_warning`**：AR10 是 per-call，警告由占位 tool_result 承载，**不复用** AR4 的轮间独立警告消息注入通路，不叠加轮间消息。

**为何**：AR10 是 AR4 的细粒度补充。短路 + 占位 tool_result 让 AR10 兑现「省掉一次无效工具执行」的增值，同时用一条 tool_result 既保消息序列合法、又向 LLM 传递纠正反馈；强制停止仍归一到 `loop_detected`，trace 词汇收敛。

**Alternatives**：①守卫自带参数比较逻辑——被否，会与 AR4 指纹漂移，且重复造轮子。②守卫用新 `StopReason.guardrail_tripped`——被否，doc 把 AR4/AR10 都归在「循环检测」语义下，复用 `loop_detected` 让 trace 词汇收敛；粒度差异由 trace 的检测来源元数据区分，不靠枚举区分。③首次命中「放行本次（执行）+ 走 AR4 轮间注入警告」——被否，放行就失去 AR10「省掉冗余执行」的核心价值，退化为 ≈AR4。④首次命中短路但**不补** tool_result——被否，有 tool_call 而无对应 tool_result 破坏消息序列不变式（与 termination-framework 给 `approval_rejected` 补占位同理）。

### D4：连续计数随 `LoopState`，相异即清零，per-run 隔离

守卫在 `LoopState` 上维护轻量连续计数（如 `last_call_fingerprint: tuple[str, str] | None`、`consecutive_repeat: int`）：

- 本次 `(tool, arg_fingerprint)` 与 `last_call_fingerprint` 相同 → `consecutive_repeat += 1`；不同 → 重置为 1 并更新 `last_call_fingerprint`。
- 计数随 `LoopState`（per-run、`run()` 内新建）生命周期，run 结束即消亡——**无全局可变状态**，天然 per-run 隔离，测试用独立 `LoopState` 即隔离。
- **不维护连续失败计数**：连续失败终止由 AR1 覆盖（见 Context / Non-Goals），守卫只追踪连续重复。

**为何**：「严格连续」要求记住「紧邻上一次」，最小状态即「上次指纹 + 当前连击数」。挂在 per-run `LoopState` 上与 AR4 历史同源、同生命周期，避免独立存储与全局态。

## Risks / Trade-offs

- [AR10 与 AR4 双命中导致重复警告] → 两者共享 `loop_warning_injected` 幂等标志：AR10 短路时置位后，AR4 轮间不再注入第二条警告；强制停止都归一到 `loop_detected`，trace 不出现两条互斥停止原因。
- [误杀合法的连续相同调用（轮询 / 重试）] → N 默认 3（连续 2 次合法、第 3 次才拦）+ 可调高阈值 + `ignore_arg_keys` 逃生舱（与 AR4 共用），降低误杀；spec 用 scenario 覆盖「连续 2 次不触发」。
- [守卫在 dispatch 前拦截改变既有 dispatch 行为] → 未命中守卫时（绝大多数调用）行为字节级不变；命中仅走既有警告 / 停止通路，不新增对外副作用；spec scenario 断言未命中路径不变。
- [连续计数与 AR4 窗口历史读写同一 `LoopState` 引入耦合] → 二者读写**不同字段**（AR4：`tool_history`；AR10：新增连续计数字段），仅共享对象与生命周期；新增字段带默认值，对既有 AR4 checker 透明（与 AR4 当初新增 `tool_history` 默认空保持向后兼容同理）。

## Open Questions

- ~~Q3：「相同工具相同参数重复 N 次」N 默认值多少、是否可配置？~~ **已决（见 D1，解决 Q3）**：N 默认 3（与 AR4 `agent_loop_repeat_threshold` 对齐），可配（Settings `guardrail_repeat_threshold` + 按次注入）。连续失败 M 已剔出本 change（归 AR1，见 Context / Non-Goals）。
- 守卫接入点选 `tool_registry.dispatch` 内部还是 `agent_loop._safe_dispatch` 前？（倾向后者：守卫属 agent-runtime 治理职责，`dispatch` 保持纯工具执行收口，短路与占位 tool_result 注入也落在此层；实施 task 1 前置核实时定）
- 占位 tool_result 的纠正文本复用 AR4 `_LOOP_WARNING_TEXT` 原文，还是为「严格连续重复 + 已短路」定制更精确的提示语（如「已跳过：相同工具相同参数连续 N 次，请换思路」）？（倾向定制以体现「已短路本次」，文案优化非本 change 阻塞项）
