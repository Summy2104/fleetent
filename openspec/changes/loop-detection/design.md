## Context

`agent_loop.py` 的主循环在每轮开头调用 `controller.should_stop(state)`（行 290 / 487），由 AR1 的 `TerminationController` 顺序评估已注册的 checker。当前注册的是 `MaxTurnsChecker` / `ConsecutiveFailuresChecker` / `ApprovalRejectedChecker`（`_build_controller`，行 46-59）。AR1 已在 `StopReason` 里预留了 `loop_detected`，并在 spec 里明确「定义了原因码但未注册 checker，故永不触发」。

问题在于：工具每次都**成功**返回时，`consecutive_failures` 始终为 0，`max_turns` 是唯一兜底。AI 反复调用同一工具（例如反复 `read_file` 同一路径、反复 `calculate` 同一表达式）却不前进时，循环会一直空转到 `max_turns`，浪费轮数与成本。

AR1 的扩展契约是「新增终止原因 = 新增 checker 并注册，不改循环体已有判定分支」。本 change 严格沿用：新增一个 `LoopDetectionChecker`，主循环只负责把每轮工具调用记入 `LoopState`，并在 checker 要求时注入一条警告消息——判定逻辑全在 checker 内。

约束（CLAUDE.md）：禁止 AI 框架；禁止 ORM；禁止全局可变状态（阈值为可注入/可配置，检测状态挂在 per-run 的 `LoopState` 上，不用模块级可变量）；新模块结构为 import → 常量 → 数据类 → 函数；mypy strict；行长 100；TDD Hard Gate；测试 mock LLM。

**与并行 change 的关系（归档顺序 / spec 协调）**：AR4（本 change）、AR19（取消传播）、AR2（迭代预算）同属波次 2 Track A，三者都依赖 AR1 终止框架（`termination.py` 已合入），且都要把 AR1 spec 中各自对应的预留原因码（`loop_detected` / `cancelled` / `budget_exceeded`）从「已定义但永不触发」激活为「已接入可触发」。为避免三者 MODIFY `agent-loop-termination` 的同一条「可扩展的终止策略注册表」需求时互相覆盖、归档顺序敏感，**本 change 不 MODIFY `agent-loop-termination`**，而在自己的新 capability（`agent-loop-detection`）里 ADD 一条「`loop_detected` 终止已接入主循环」需求。AR1 spec 中「预留原因码尚未激活」的表述由本 change 起被本条 ADDED 需求超越；三个 change 各自独立 ADD，互不引用、无归档冲突，归档顺序可任意。依赖上仅要求 AR1 已先行合入（已满足）。

## Goals / Non-Goals

**Goals:**
- 提供一个注册进 AR1 终止框架的 `LoopDetectionChecker`，复用 `loop_detected` 原因码。
- 在主循环层做粗粒度检测：以双信号识别「反复调用同一工具却毫无进展」——参数指纹精确重复（信号 A）∨ 成功结果摘要停滞（信号 B，覆盖易变参数盲区）。
- 两段式响应：首次命中注入警告提示（给 AI 一次自救机会），AI 忽略仍重复则强制终止。
- 检测阈值可注入 / 配置，`loop_detected` 终止写入 trace。
- `run()` 与 `run_stream()` 两路径均接入。

**Non-Goals:**
- 不做细粒度「相同工具相同参数连续 N 次」的工具调用守卫（AR10，波次 3）——本 change 是主循环粗粒度层。
- 不做语义级「进展判定」（如用 LLM 判断是否在前进）——粗粒度检测仅基于参数指纹重复（信号 A）与成功结果摘要的字节级相同（信号 B），不理解结果语义、不额外调用 LLM。
- 不改 `max_turns` / `consecutive_failures` / `approval_rejected` 的判定与阈值。
- 不引入新依赖。

## Decisions

### D1：循环检测实现为注册进 AR1 框架的 checker，而非改主循环
新增 `src/fleetent/loop_detector.py`，提供 `LoopDetectionChecker`（实现 `TerminationChecker` Protocol：`check(state: LoopState) -> StopReason | None`）。`_build_controller` 在 `MaxTurnsChecker` 等之后 `register(LoopDetectionChecker(...))`。

**为何**：这正是 AR1 spec「新增终止原因通过新增 checker 接入、不改主循环已有判定分支」所要求的扩展方式，与 AR5（错误分类）选择「查表纯函数」不同——循环检测是「依据 per-run 状态判定是否该停」的策略，天然契合 checker 模型，且需读 `LoopState`，正是 checker 的输入。
**Alternatives**：①在主循环 `while` 体里内联检测逻辑——被否，违反 AR1 扩展契约，且让循环体继续膨胀；②做成独立的「守卫层」拦在 dispatch 前——被否，那是 AR10 细粒度守卫的职责，本 change 是主循环层粗粒度终止。

### D2：检测信号 = 双信号（参数指纹精确重复 ∨ 结果停滞无进展）
粗粒度检测的语义锚点是 agent-runtime.md 的「反复调用同一工具却**毫无进展**」。仅看「工具名 + 参数指纹」会在参数携带易变字段（时间戳 / 随机 id / 自增 attempt 计数 / 翻页游标占位）时漏判——参数每次不同、指纹每次不同，却在原地打转。因此采用两个互补信号，任一在窗口内达到阈值即视为一次循环命中：

- **信号 A（精确重复，快速路径）**：`LoopState` 每次工具调用后 append `(tool_name, arg_fingerprint, result_digest)`。`arg_fingerprint` 由 `loop_detector` 的纯函数对参数归一化（JSON 解析→按 key 排序→序列化；解析失败则对原始串取指纹），使语义相同、键序不同的参数得同一指纹。checker 判定「窗口内同一 `(tool_name, arg_fingerprint)` 出现 ≥ 阈值」。覆盖最典型的「一字不差重复调用」。
- **信号 B（结果停滞，无进展路径）**：checker 判定「窗口内同一 `tool_name` 的**成功**调用产出**相同 `result_digest`** ≥ 阈值，**不论参数是否变化**」。这是「毫无进展」的直接度量，天然覆盖信号 A 的易变参数盲区。`result_digest` 为对结果内容归一化后的哈希，**截首尾并限长**（如首尾各 1KB）以控成本；粗粒度，不做语义比对。

边界约束：
- 信号 B **只计成功且结果相同**的调用；**失败结果不计入**（连续失败已由 AR1 `consecutive_failures` 覆盖，避免双重计数）。
- 结果**每次不同**（时钟工具、游标在推进、搜索结果在变）→ `result_digest` 不同 → 信号 B 不命中，不误杀正常推进的工具。
- 参数**与**结果都不同 → 两信号均不命中，正常放行。

可选逃生口（默认关闭）：一个可配置的 `loop_detect_ignore_arg_keys` 参数键忽略表，默认空；置为非空时在算 `arg_fingerprint` 前剔除这些键。**默认不启用**——维护「易变字段黑名单」脆弱且 key 名因工具而异；信号 B 已是规避易变参数的主手段，忽略表仅作个别工具的精调逃生口。

**为何**：把检测锚点从「参数相同」回归到「无进展」，与 agent-runtime.md 对粗粒度层的定义一致；信号 B 用结果摘要而非参数，堵住易变参数盲区；`result_digest` 截断限长把比对成本压到常数级，排除失败结果避免与 `consecutive_failures` 重叠。精确的「工具+参数完全重复」细粒度模式检测仍留给 AR10（波次 3），两层不重叠。
**Alternatives**：①仅用参数指纹（原方案）——被否，易变参数盲区会漏判「原地打转」，偏离「无进展」语义；②比对**完整**结果——被否，结果可能极大，故改用截首尾限长的 `result_digest`；③引入 LLM 判断是否有进展——被否，违反「粗粒度、不额外调用 LLM」目标且增成本；④维护易变字段名黑名单作主机制——被否，脆弱且 key 名千变万化，降级为默认关闭的可选逃生口。

### D3：两段式响应（先警告、后终止），阈值可配置
checker 内部按命中次数分两段：
- 第一次达到「重复阈值」：返回一个「请求注入警告」的信号，主循环据此向 `messages` 追加一条 system/user 角色的警告提示（内容形如「检测到你正在重复调用同一工具且似乎没有进展，请改用其它方式或直接给出当前结论」），并在 `LoopState` 标记「警告已注入」。**此轮不终止**。
- 警告注入后若同一模式再次达到阈值（即 AI 忽略警告继续重复）：checker 返回 `StopReason.loop_detected`，主循环强制终止。

阈值 `agent_loop_repeat_threshold` 默认 **3**（任一信号 A/B 在窗口内达到 3 次即视为一次命中），经 pydantic `Settings` 暴露，可由 `.env` / `config/settings.yaml` 覆盖；同样支持 `run()` / `run_stream()` 的参数注入（沿用 `max_turns` 的注入风格，便于测试传小值）。

**检测窗口大小（propose 阶段定死，不暴露为配置）**：检测只看「最近 N 条工具调用历史」，窗口 N 固定为 `max(2 × repeat_threshold, 6)` 的模块级派生常量（即默认阈值 3 时窗口 6），随阈值绑定、不单独暴露配置项。理由：窗口大小直接影响「多久以前的重复还算同一个循环」的可观察阈值语义，留作可调配置会让同一阈值在不同部署下表现不一致；与阈值绑定为派生量即可覆盖「警告轮 + 终止轮」两段所需的回看长度。`LoopState` 历史按此窗口 FIFO 截断，不保留全量历史。

**为何**：直接硬切会误伤「确实需要多次调用同一工具但每次参数其实不同」之外的边界场景，也违反 agent-runtime.md 明确写的「检测到循环 → 注入警告提示；AI 忽略仍重复 → 强制停止」。默认 3 与 `agent_max_consecutive_failures` 同量级，保守不激进。
**Alternatives**：①一命中即终止——被否，违反 agent-runtime.md 两段式要求，易误杀；②无限次只警告不终止——被否，AI 可能持续忽略，达不到止损目的。

### D4：警告注入消息不发起额外 LLM 调用，角色定为 user
警告以一条普通消息追加进 `messages`，在**下一轮**正常 LLM 调用时随上下文一起送达 AI，不为注入单独发请求。

**警告消息角色（propose 阶段定死）= `user`**：循环警告紧随一批 `tool` 结果之后注入，而系统提示通常已在序列首位以 `system` 占据。若警告也用 `system`，在 OpenAI 兼容后端上可能与已有 system 消息相邻而被 `message_hygiene.sanitize` 的同角色合并/折叠规则改写，降低警告的独立可见性；用 `user` 角色（语义为「来自运行时的纠偏指令」）可避免同角色合并、保证 AI 在下一轮明确读到。该角色在 propose 阶段定死，不留待实现期选择。

**为何**：零额外成本、零额外延迟；与主循环「每轮组装 messages → 调一次 LLM」的节奏一致。
**Alternatives**：①单独发一次「纠偏」LLM 调用——被否，多一次成本与延迟，且打乱循环节奏；②用 `system` 角色——被否，见上，易被同角色合并而削弱可见性。

### D4b：警告轮与压缩同轮的可见性保证
注入警告的那一轮若恰好满足压缩触发条件（`maybe_compress` 命中），需保证警告不被压缩摘要静默吞掉。落点：警告消息在该轮压缩**之后**、紧邻下一次 LLM 调用前 append（或纳入压缩的 `keep_tail` 保留尾窗），使其必然出现在送往 LLM 的消息序列中而非被卷入被摘要的历史段。

**为何**：警告的全部价值在于「AI 下一轮能读到」；若它先入 `messages` 再被同轮压缩当作普通历史摘要掉，AI 将看不到纠偏提示，两段式第一段形同失效。实现首步以「警告轮恰逢压缩」的用例验证警告对 AI 可见（见 spec 对应 ADDED 需求与 tasks 5.x）。
**Alternatives**：不处理、依赖运气——被否，压缩对警告轮的吞噬是确定性风险，须显式保证。

### D5：trace 与终止收尾复用 AR1 出口
`loop_detected` 终止时，`stop_reason = StopReason.loop_detected`，经现有 `log_run(..., stop_reason=...)` 出口（agent_loop.py 行 389 / 589）写入 trace，无需新增 trace 字段或新出口。

**为何**：与 AR1 `max_turns` 等终止原因写 trace 的方式完全一致，改动最小、统计口径统一。

## Risks / Trade-offs

- [误判：合法地多次调用同一工具但实为正常流程（例如分页读取，参数每页不同且结果每页不同）] → 信号 A 看参数指纹（参数不同则不计入）、信号 B 看成功结果摘要（结果不同则不计入）；分页读取参数与结果都在变，两信号均不命中。两段式先警告再终止进一步降低误杀，阈值可配置上调。
- [漏判：AI 用「参数表面不同但其实原地打转」绕过（如表达式加无意义空格、参数带时间戳/随机 id）] → 这正是信号 B 的目标场景：只要这些调用的**成功结果摘要相同**，信号 B 即据「无进展」命中，不受参数抖动影响。仅当 AI 同时让参数与结果都表面变化才可能逃过粗粒度层——此类精确「工具+参数完全重复」的细粒度模式检测留给 AR10（波次 3），design 明确范围边界。
- [信号 B 比对结果摘要的成本 / 误伤] → `result_digest` 截首尾限长（如首尾各 1KB）后取哈希，比对为常数级；只对**成功且字节级相同**的结果计数，结果含任何实质变化即不同，不做语义判等，避免误伤。
- [`LoopState` 扩展历史可能无界增长占内存] → 仅保留近期窗口（窗口大小与阈值同量级的小常量），按 FIFO 截断，不保留全量历史。
- [`run_stream()` 注入警告后流式语义] → 警告仅进入 `messages`，不向客户端 yield 额外事件，用户端可见行为不变（最终仍以 `done` 收尾或 `loop_detected` 提前收尾）。
- [警告注入恰逢压缩轮，警告被压缩摘要吞掉而对 AI 不可见] → 警告在该轮压缩之后、下一次 LLM 调用前 append（或纳入 `keep_tail` 保留尾窗），保证出现在送往 LLM 的消息序列中（见 D4b）；以「警告轮恰逢压缩」用例守卫可见性。
- [与 AR1 spec 的协调] → 本 change 不 MODIFY `agent-loop-termination`，改为在自己的新 capability 里 ADD「`loop_detected` 终止已接入主循环」需求；与并行 change（AR19 / AR2）各自独立 ADD，无归档覆盖冲突（见 ## Context）。

## Open Questions

- （无）检测窗口大小与警告消息角色已在 D3 / D4 于 propose 阶段定死，不留待实现期决策。
