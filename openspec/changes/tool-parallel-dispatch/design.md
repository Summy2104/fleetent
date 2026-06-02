## Context

`agent_loop.run()`（主循环 tool_calls 段行 ~739–843）与 `run_stream()`（行 ~1117–1160）当前对 LLM 一轮返回的多个 `tool_calls` **顺序逐个**处理：每个 `tc` 依次跑 AR10 guardrail（`evaluate_guardrail`）→ 若是 `_SUB_AGENT_TOOL` 走 `SubAgentExecutor`，否则按 `get_risk_level` 对 medium/high 经 `_default_gate.request_approval` 审批 → `_safe_dispatch` 执行 → 回填 `role:"tool"` 消息 + `record_tool_call` + `consecutive_failures` 累计。本轮工具耗时因此线性叠加。

已就位的复用基础（无需重做）：
- **AR19 `CancelToken`**（`cancellation.py`）：run-level token 在 `run()` 行 661 / `run_stream()` 行 992 绑定为 `token`，单向流入 `_safe_dispatch`。
- **T2 per-tool 超时**：`_safe_dispatch`（行 313–329）已为每个工具派生 `child = CancelToken(deadline=now+timeout, parent=cancel_token)`，并用 `asyncio.wait_for` 兜底硬停；超时归一化为 `failed=True`。这意味着**单工具的取消 / 超时 / 资源中止已经完备**——AR3 只需保证「一批」共享同一 run-level `token`、并发跑这些已自带保护的 `_safe_dispatch`。
- **AR6 sanitize**（`message_hygiene.py`）：每轮 LLM 调用前校验 assistant→tool 配对完整性；AR3 的回填必须产出合法序列以不触发其修复 / 报错。
- **AR1 终止框架**（`termination.py`）：`cancelled` 等原因码经 `controller.should_stop(state)` 在每轮检查点判定；AR3 不新增 checker、不改判定分支。

约束（CLAUDE.md）：禁止 AI 框架；禁止 ORM；禁止全局可变状态（并发上限经 `Settings` 注入，可 monkeypatch）；不吞异常（`_safe_dispatch` 已归一化工具异常，AR3 不得用 `gather(return_exceptions=True)` 静默吞掉非工具异常——见 D4）；mypy strict；行长 100；TDD Hard Gate；测试 mock LLM。

**与同轨依赖的关系**：AR3 是 Track A 波次 4 收尾，依赖 AR1·AR6·AR19 均已归档合入。AR3 **不 MODIFY** 任何既有 capability：单 `tool_call` 行为字节级不变（Non-Goal），新行为全部 ADDED 到新 capability `tool-parallel-dispatch`。无归档顺序敏感性。

## Goals / Non-Goals

**Goals:**
- 同一轮内多个相互独立的 `tool_calls` 并行执行（`asyncio.gather`），降低本轮端到端时延。
- 结果按**原 `tool_calls` 顺序**回填 `messages`，tool-pair 配对 / 顺序合法，AR6 sanitize 不触发修复。
- 并行批次共享 run-level `cancel_token`；取消 / deadline 命中时全批中止、收尾消息合法（无半截 tool-pair）。
- 多 medium/high 风险工具审批串行（逐个过 gate）、全批准后再并行执行——明确、安全、可单测。
- 单工具失败隔离；`consecutive_failures` 与 AR4/AR10 loop-detection 逐结果记录，语义等价顺序执行。
- 单轮并发上限可配置（默认见 D7），超限分批。
- `run_stream` 并行期流式事件按原序 yield。
- N=1 与现状字节级等价。

**Non-Goals:**
- 不改单 `tool_call`（N=1）现有行为（字节级等价）。
- 不改工具注册 / schema / `check_tool_access` 访问控制。
- 不引入新依赖（仅 `asyncio` 标准库）。
- 不做跨轮并行（只并行同一轮内的多 `tool_calls`）。
- 不改 AR19 token 接口、T2 超时、AR6 sanitize、AR1 终止判定、permission_gate 门机制、`SubAgentExecutor` 深度约束。
- 不为「有状态 / 同容器」工具做细粒度并发安全改造（见 D5 边界）。

## Decisions

### D1：原序回填用 `asyncio.gather`（返回保序），不用完成序

把顺序 `for tc` 重构为**三阶段**：

1. **阶段一（串行、保原序）—— 计划**：遍历原 `tool_calls`（保持索引 0..N-1），对每个 `tc` 跑 AR10 `evaluate_guardrail` 与（medium/high）permission_gate 审批（审批串行，见 D3）。为每个索引产出一个「计划槽」：要么是**占位结果**（guardrail 短路 / stop、审批被拒、sub_agent 特例 见 D6），要么是**待执行**（记下 `name` / `args` / `tc.id`）。
2. **阶段二（并发）—— 执行**：对所有「待执行」槽，用 `asyncio.gather(*[_safe_dispatch(...) for ...])` 并发执行（受 D7 并发上限约束，可分批）。`gather` 的返回 list **顺序 = 入参 coroutine 顺序**，与原索引一一对应。
3. **阶段三（串行、保原序）—— 回填**：按原 `tool_calls` 索引 0..N-1 顺序，把每个槽的结果（占位或执行结果）回填为 `role:"tool"` 消息（`tool_call_id = tc.id`）、`record_tool_call`、累计 `consecutive_failures`（见 D4）。

**为何用 `gather` 保序而非完成序**：OpenAI 协议要求 assistant 消息后紧跟的 tool 结果消息**与 `tool_calls` 顺序对应**（AR6 sanitize 校验配对完整性）。`asyncio.gather(*coros)` 文档保证「结果顺序与输入 awaitable 顺序一致」（与完成先后无关），因此并发执行后无需排序即得原序——这是最简单且零额外记账的保序手段。若改用 `asyncio.as_completed`（完成序），则须额外维护 `future→index` 映射再重排回原序，复杂且易错，无收益（回填本就在全批完成后做）。

**Alternatives**：①`as_completed` + 重排——被否，额外映射 / 重排复杂，且无法边完成边回填（消息序列须整段合法），收益为零；②`TaskGroup`（3.11+）——保序需自己持有 task 列表再按序取 `.result()`，与 `gather` 等价但更多样板，且需确认运行时 Python 版本，`gather` 已足够。

### D2：阶段切分——guardrail / 审批在阶段一（串行），dispatch 在阶段二（并行）

阶段一保持串行的原因：AR10 `evaluate_guardrail` 依赖 `state`（记录 back-to-back 重复），permission_gate 审批需逐个交互——二者都是**有顺序语义的决策**，并非可并行的纯计算。只有 `_safe_dispatch`（真正的工具 IO）才并行化。这把「决策」与「执行」解耦：决策阶段确定哪些工具进批，执行阶段并发跑，回填阶段按序落地。

**为何**：guardrail 的重复检测、审批的串行交互天然不可乱序并发；强行并发会破坏 AR10 语义、并令审批 UX 混乱。把并行限定在纯 IO 的 `_safe_dispatch` 是最小且安全的并行面。
**Alternatives**：把 guardrail 也并入并行——被否，破坏 AR10 顺序语义与 `state` 一致性。

### D3：permission_gate 审批策略 = 审批串行、全部批准后并行执行

一轮内多个 medium/high 风险工具：在阶段一**逐个**调 `_default_gate.request_approval`（串行，保持原索引顺序），每个等待其决策返回后再处理下一个。被拒的工具沿用现有 `approval_rejected=True` + 占位结果（`"tool execution {decision}: ..."`），**不进并行批**；被批准的工具进入阶段二的并行批。阶段二只对「已全部完成审批且被批准」的工具集合 `gather`。

**为何（关键决策）**：
- **安全 / 可审计**：审批是人工介入的安全闸；串行审批使每个高危操作有独立、有序、可理解的审批提示，避免同一时刻向用户推送 N 个并发审批请求造成混淆或误批。
- **可单测**：串行审批是确定性顺序，单测可逐个断言 gate 调用与决策；并发审批的事件交错难以稳定断言。
- **gate 并发安全性留作非必需**：`permission_gate` 用 `asyncio.Event`，并发 `request_approval` 在 asyncio 单线程下不会数据竞争，但**审批语义**（用户一次看清一个高危请求）才是采用串行的真正理由——不依赖 / 不论证 gate 的并发安全即可得到安全策略。
- 「先全部审批、后并行执行」保证：任一被拒不会让已并行启动的其他高危工具产生副作用（执行尚未开始）。

**取舍**：串行审批使审批阶段不并行（N 个 medium/high 工具的审批时延叠加）。可接受——审批是人工节拍（分钟级超时），其时延由人决定，并行化审批无实际收益且损害安全；真正耗时的工具 IO 仍在阶段二并行。
**Alternatives**：①并发审批（`gather` request_approval）——被否，UX 混乱、单测不稳、安全收益为零；②审批与执行交错并行——被否，破坏「全批准后才执行」的安全不变量。

### D4：失败隔离与 `consecutive_failures` / loop-detection 计数

- **失败隔离**：每个工具走各自的 `_safe_dispatch`，它已把工具崩溃 / 超时归一化为 `(error_text, failed=True)`（不抛）。因此并行批中单工具失败**天然不影响**同批其余——`gather` 收到的是 N 个 `(result, failed)` 元组，无异常传播。
- **不可用 `return_exceptions=True` 掩盖真异常**：`_safe_dispatch` 内部已 `except Exception` 归一化，正常不会向 `gather` 抛异常。AR3 **不**对 `gather` 传 `return_exceptions=True`——若 `_safe_dispatch` 之外（如调度框架本身）真抛出非预期异常，应让它冒泡（不吞异常，CLAUDE.md），而非被 `gather` 静默收集成结果。
- **`consecutive_failures` 计数语义（明确定义）**：保持与顺序执行**逐结果等价**——在阶段三按原序遍历每个执行结果，逐个 `state.consecutive_failures = state.consecutive_failures + 1 if failed else 0`。即：一个成功结果将其清零，一个失败结果 +1，**按原 `tool_calls` 顺序逐个套用**。这与现状（顺序 dispatch 时同样逐个更新）**完全一致**，不引入「全部失败才 +1」之类新语义。`record_tool_call`（AR4/AR10 loop-detection 的窗口记录）同样在阶段三按原序逐结果调用，窗口内容与顺序执行等价。

**为何逐结果而非批级**：批级计数（如「全失败才 +1」）会改变 AR2 `max_consecutive_failures` 终止时机的语义，且与 N=1 不等价。逐结果套用是唯一与现状一致的定义；阶段三按原序回填本就逐个遍历，自然落到逐结果更新。
**Alternatives**：批级聚合计数——被否，改变既有终止语义、N=1 不等价。

### D5：共享 sandbox 容器的并发执行边界（SB2 session 容器复用）

`SandboxManager.acquire`（`sandbox_manager.py` 行 95）对同一 `session` scope 返回**同一个容器**（`ws_id`）。若同一轮有多个 `run_code`，并行 `gather` 会对**同一容器并发 `docker exec`**——多个 exec 在同一容器文件系统 / 进程空间内可能相互干扰（有状态副作用、竞态）。

**决策（边界）**：AR3 对「同容器 / 有状态」工具采取**保守串行化**——把 `run_code`（及任何标注「同容器有状态」的工具）在并行批内**按其共享资源键串行执行**，不同键之间仍可并行；非沙箱、无共享状态的工具（HTTP 抓取、查询类）正常并行。最小实现：阶段二对 `run_code` 这一类工具按「session 沙箱容器」分组，组内串行、组间与其它工具并行（可用 `asyncio.Lock` per 容器键，或把同键工具收敛为一个顺序子协程再纳入 `gather`）。

**为何**：SB2 的容器复用是为跨调用保留环境，并非为并发 exec 设计；同容器并发 exec 的隔离性无保证，贸然并行可能产生难复现的脏状态。串行化同容器 exec 以零正确性风险换取「同容器多 run_code 不加速」——可接受，因为同一轮内对同一沙箱的多次代码执行通常本就有隐含顺序依赖。
**取舍**：同 session 多个 `run_code` 不获得并行加速。可接受且安全；跨 session / 不同容器的 `run_code` 仍并行。
**Alternatives**：①接受同容器并发 exec 并文档化风险——被否，正确性风险不可控；②为沙箱实现 per-exec 子容器 / 命名空间隔离——被否，超出 AR3 范围（属沙箱轨），且与 SB2 复用目标冲突。

### D6：sub_agent 嵌套与 AR3 的关系

`_SUB_AGENT_TOOL`（`agent_loop.py` 行 764）已由 `SubAgentExecutor`（`sub_agent.py`）用 `asyncio.gather` 并行**子 agent**，最大深度 1（子 agent 内不再起 sub_agent）。AR3 的并行是**主循环对同一轮 tool_calls** 的并行，与 sub_agent 的「并行多个子任务」是**不同层**。

**决策**：
- AR3 阶段一把 `sub_agent` 调用当作一个普通「待执行槽」纳入并行批（它本身就是一个 awaitable 工具调用），其内部仍由 `SubAgentExecutor` 自行 `gather` 子任务——两层并行互不干扰、不叠加放大并发（sub_agent 内部不触发主循环并行，因为子 agent 是独立 run，深度 1 约束由 `is_sub_agent` 守卫不破）。
- 子 agent 的 `run()` 同样会接到 AR3 重构后的并行调度，但**深度 1 约束**（子 agent 内 `is_sub_agent=True`，行 764 的 `_SUB_AGENT_TOOL` 分支被 `and not is_sub_agent` 关闭）保证子 agent 不再生成 sub_agent，故并行嵌套深度不增。

**为何**：两层并行正交；保留现有 `SubAgentExecutor` 与深度守卫即可，不需特殊处理。把 sub_agent 简单视为并行批中的一个 awaitable 槽是最小改动。
**Alternatives**：把 sub_agent 排除出并行批单独串行——非必需，sub_agent 本就是 awaitable，纳入批更一致；但实现上保留现有 sub_agent 特例分支（它产出的是字符串 result），归一化为一个槽即可。

### D7：单轮并发上限（可配置，默认值）

`Settings` 新增 `agent_tool_parallel_max: int`，**默认 8**。阶段二并行执行时，若待执行工具数 > 上限，则**分批**（每批至多 `agent_tool_parallel_max` 个 `gather`，批间串行），所有批完成后统一进阶段三回填——回填仍严格按原 `tool_calls` 索引顺序（分批不改变最终回填顺序）。`agent_tool_parallel_max <= 1` 时退化为全顺序执行（等价现状，提供「关并行」开关）。经 `.env` / `settings.yaml` 覆盖、测试可 monkeypatch。

**为何默认 8**：与典型 LLM 单轮 tool_calls 规模相称（多数 ≤ 几个），8 足以吃满常见并行收益，又不至于一轮打爆下游（HTTP 连接、沙箱、MCP）资源；保守且可调。`<=1` 退化为顺序，给出安全回退。
**取舍**：上限是全局而非 per-工具类型的细粒度限流——足够简单、可单测；更精细的 per-资源限流超出 AR3 范围。
**Alternatives**：①无上限（一把 `gather` 全部）——被否，N 大时打爆资源；②per-工具类型配额——被否，过度设计，AR3 不需要。

### D8：`run_stream` 并行期流式事件顺序

`run_stream` 的并行执行同样三阶段，但要兼顾流式事件：
- `tool_call` 事件：在阶段一按原序为每个 `tc` yield（执行尚未开始，按索引顺序发出，客户端先看到「将执行哪些工具」）。
- `tool_result` 事件：在阶段二全批 `gather` 完成后，于阶段三**按原 `tool_calls` 索引顺序**逐个 yield `tool_result`，紧随其后 append 对应 tool 消息——与 `run()` 回填同序。即客户端看到的是「N 个 tool_call（原序）→ N 个 tool_result（原序）」。
- 取消 / 失败时：对应索引仍 yield 一个 `tool_result`（含取消 / 错误内容占位），保证 N 个 tool_call 对应 N 个 tool_result，不泄漏半截事件。

**为何（不流式发完成序）**：并行执行虽可能某工具先完成，但若按完成序 yield `tool_result`，客户端看到的结果顺序与 `tool_call` 顺序错位、且 messages 回填须原序——双序不一致徒增客户端复杂度。统一「全批完成后按原序 yield」让流式语义与 messages 一致、可理解。代价是 `tool_result` 不能边完成边流出（须等全批），但本轮工具结果本就要整段合法回填后才进下一轮 LLM，无实质损失。
**Alternatives**：边完成边 yield `tool_result`（完成序）+ 标注 index——被否，客户端需自行重排、与 messages 序不一致，复杂度转嫁客户端。

## Risks / Trade-offs

- [`asyncio.gather` 中某 coroutine 抛非工具异常会令整批 gather 抛出] → `_safe_dispatch` 已 `except Exception` 归一化，正常路径不抛；AR3 不用 `return_exceptions=True` 掩盖，真异常应冒泡（不吞异常）。阶段三回填仅处理 `(result, failed)` 元组。
- [同 session 多个 `run_code` 并发污染共享容器] → D5 对同容器有状态工具按资源键串行化，组间仍并行；正确性优先于该类工具的并行加速。
- [取消命中时部分工具已完成、部分在途] → 共享 run-level token + `_safe_dispatch` 各自 child token（含 deadline + `asyncio.wait_for` 硬停）保证在途工具被中止（`run_code` 走 `docker rm -f`）；阶段三对每个原索引都回填一条 tool 消息（已完成的填结果，被取消 / 超时的填归一化的 failed 占位），N 个 tool_calls 必有 N 条 tool 结果消息，AR6 sanitize 不触发半截 tool-pair 修复。
- [并行改变了副作用工具的相对时序] → 同一轮 LLM 发出的多 tool_calls 协议上视为可并发；有顺序依赖的工具由 LLM 拆到不同轮，或 D5 的同容器串行兜底；文档化此语义。
- [审批串行使多高危工具审批时延叠加] → D3 取舍：审批是人工节拍，串行换安全与可审计，工具 IO 仍并行。
- [N=1 回归风险] → 三阶段重构对 N=1 须字节级等价；tasks 首个测试组即锁定 N=1 等价（messages、事件序、计数）。

## Open Questions

- 无阻塞性未决项。D5 的「同容器串行化」最小实现（per 容器键 `asyncio.Lock` vs 同键收敛为顺序子协程）属实现细节，二者可观察行为一致，留待 apply 阶段按代码最简方式选定，不影响 spec。
