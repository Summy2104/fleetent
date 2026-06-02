# Wave-3 Apply 决策日志

> 全自主 apply 期间，遇到的冲突 / Open Question 及其自解决策记录，供 zy 最后核实。
> 每个 change 一节：遇到什么、怎么解的、影响。
> 执行顺序见 `v1.0-roadmap.md` 波次 3；硬约束 AR18(cost-budget-control) → MR2(cost-aware-routing)。
> **顺序修订（见下方「执行顺序自解决策」）**：AR20 提前到第 2 位，因其提供 T2/SB7 依赖的 `CancelToken.parent` 原语。

## 执行顺序自解决策（2026-06-01）

执行 #2 原定 tool-timeout(T2) 时核实发现：T2 与 SB7 的 spec 均**强制**依赖 `CancelToken.parent` 字段（run 级取消经 `parent` 链接传播到在途工具），而该 `parent` 原语在各 spec 中被明确**归属于 AR20（sub-agent-lifecycle）对 AR19 `cancellation.py` 的增量补全**（见 `sub-agent-lifecycle/design.md` D3）。当前 `cancellation.py` 的 `CancelToken` 只有 `deadline`、无 `parent`。

- **冲突**：原顺序把 AR20 排第 12，但 T2(#2)/SB7(#6) 依赖它先落地。roadmap 依赖列只标 T2 dep=AR5·AR19，未含 AR20——这是 spec 作者后续引入的更细耦合。
- **决策**：把 **sub-agent-lifecycle(AR20) 提前为 #2**，先落地 `parent` 原语 + `sub_agent_runs` 表，再做 T2、SB7。其余顺序与轨道分组不变；AR18→MR2 硬约束仍满足。
- **核实**：`compression-trace` 的 "parent" 仅指 `TRACE_PATH.parent`（文件路径），与 CancelToken 无关，不受影响。

## 执行进度（修订后顺序）

| # | 阶段/轨 | change | roadmap | 状态 |
|---|---|---|---|---|
| 1 | C | tool-arg-sanitization | T3 | ✅ 已完成 |
| 2 | A | sub-agent-lifecycle | AR20 | ✅ 已完成 |
| 3 | C | tool-timeout | T2 | ✅ 已完成 |
| 4 | C | tool-result-truncation | T4 | ✅ 已完成 |
| 5 | C | tool-call-guardrails | AR10 | ✅ 已完成 |
| 6 | F | sandbox-output-truncation | SB6 | ✅ 已完成 |
| 7 | F | sandbox-exec-timeout | SB7 | ✅ 已完成 |
| 8 | B | compression-trace | AR16 | ✅ 已完成 |
| 9 | B | compression-anti-flap | AR17 | ✅ 已完成 |
| 10 | E | mcp-degradation | MCP4 | ✅ 已完成 |
| 11 | H | scheduled-task-session-binding | S3 | ✅ 已完成 |
| 12 | A | cost-budget-control | AR18 | ✅ 已完成（评审后：cost 删，保留 turns/tokens 五层） |
| 13 | D | cost-aware-routing | MR2 | ⛔ 评审后回退/删除（无 cost 信号） |

---

## tool-arg-sanitization（T3）— feat/tool-arg-sanitization

**实现：** 在 `eval_logger` 序列化层（与 `_placeholder_images` 同层、同范式）新增 `_redact_tool_calls`/`_redact_tool_call`：序列化 assistant 消息时，解析其 `tool_calls[].function.arguments`（LLM 产出的原始 JSON 字符串），把**顶层参数名**命中 `sandbox_secrets.is_sensitive_name` 的值替换为占位符 `[REDACTED]`，再重新序列化回 JSON 字符串保持 trace 形态。`_serialize` 改为 `_redact_tool_calls(_placeholder_images(...))` 组合两道脱敏。复用 SB5 单一规则源（`from fleetent import sandbox_secrets`，monkeypatch `SENSITIVE_TOKENS` 即时生效），未在 `eval_logger` 另立常量。

**自解决策（针对 design 的 Open Questions，全部自行拍板并记录）：**
1. **占位符形态**：design OQ 问 `***` / `[REDACTED]` / `ab***yz` 哪种。**定为 `[REDACTED]`**，提为模块级常量 `REDACTED_PLACEHOLDER` 作单一事实来源（测试引用该常量、不硬编码）。理由：审计语义最清晰、不暴露任何原值前后缀，且 `_placeholder_images` 本就用方括号风格 `[图片：…]`，方括号占位符与既有范式一致。
2. **是否在 trace entry 加"曾发生脱敏"布尔标记**：design OQ 倾向需要。**本 change 不做**。理由：spec 的 4 条 Requirement 与全部 scenario 均只约束"逐条消息脱敏"，未要求该标记；加它需把状态从逐消息 transform 上抛到 entry 组装层，破坏 `_serialize` 的纯函数/逐条洁净性。归属与形态留作后续 change 与 trace owner 对齐（design 原文亦许可"实现期对齐"）。
3. **脱敏粒度**：只处理解析后 arguments **顶层键**（即工具的直接参数名）。嵌套 dict 不递归——spec scenario 皆为顶层参数，递归属过度工程且易误杀；与"仅名过滤"边界一致。
4. **非法 JSON 容错**：`function.arguments` 解析失败（`JSONDecodeError`/`ValueError`）或解析结果非 dict 时，原样返回该 tool_call、不抛异常（退化为既有行为），满足 design Risks 的容错要求。
5. **路径穿越保护（任务 5.1）**：按 design D3 仅文档重定向，本 change 不产出 safe_path 代码/测试。

**影响：**
- 改 `src/fleetent/eval_logger.py`（+1 常量 +2 函数 +`_serialize` 组合）、`tests/test_eval_logger.py`（+9 测试）。
- 测试：`test_eval_logger.py` 36 passed（既有 27 + 新增 9）。全量 1036 passed（基线 1027 + 9），**170 个失败为 `feature/zhangyang` 基线预存**（webhook 等，与本 change 无关，已 stash 对比确认零回归）。
- ruff：仅对改动文件 `format`+`check` 全绿（未跑全仓 `ruff format`，避免重排无关文件）。
- mypy：`uv run mypy src` 74 errors，与基线一致，`eval_logger.py` 零错误，无新增。

**需 zy 核实：**
1. 占位符定为 `[REDACTED]`（自解决策 #1）是否认可。
2. 不加"曾脱敏"布尔标记（自解决策 #2）是否认可；如需，后续接 trace entry 层。
3. 仅脱敏顶层键、不递归嵌套（自解决策 #3）是否够用作 v1.0 起点。

## sub-agent-lifecycle（AR20）— feat/sub-agent-lifecycle

**实现：**
- 新增 `src/fleetent/sub_agent_lifecycle.py`：`SubAgentState`（StrEnum，6 态）、`SubAgentLifecycle`（dataclass，对应 `sub_agent_runs` 一行）、`validate_transition`（合法迁移表 + 非法 raise `ValueError`）、`init_db`/`upsert`/`query_by_parent`（标准库 `sqlite3`，`DB_PATH` 从 `user_store` re-export 可 monkeypatch，复用 `_conn` 惯例）、`resolve_timeout`（优先级 call > config(Settings) > 默认 300）。
- `cancellation.py`：`CancelToken` 增量加可选 `parent: CancelToken | None = None`，`is_cancelled()` 在自身 `_cancelled`/deadline 外 OR 上 `parent.is_cancelled()`（纯加法，默认 None，既有用法零影响）——AR20 对 AR19 的增量补全。
- `config.py`：新增 `sub_agent_timeout_seconds: int = 300`（env-first，同 `agent_max_turns` 款式）。
- `sub_agent.py`：`SubAgentExecutor.run` 新增可选 kwarg `timeout_seconds`/`cancel_token`（缺省与现状等价）；`_run_one` 在各生命周期点写记录，构造 `CancelToken(deadline=now+timeout, parent=batch_token)` 透传 `agent_loop.run(cancel_token=...)`；据 `child.is_cancelled()` + deadline 是否已过区分 `timed_out`（自身超时）/`cancelled`（父/外部取消）；异常记 `failed`。

**自解决策（记录供核实）：**
1. **顺序前置**：AR20 由 #12 提前到 #2，因 T2/SB7 依赖其 `parent` 原语（见上方「执行顺序自解决策」）。
2. **热路径少写一次 fsync**：正常路径首条持久化记录直接是 `running`（created_at + started_at 同时落），`pending` 仅在「启动前即被外部取消」分支持久化（pending→cancelled、started_at 为 None）。理由：正常路径 pending→running 之间无 await、几乎瞬时，独立进程几乎不可能恰好查到 pending；省一次同步 sqlite commit（fsync）对并发延迟有实质改善（见下）。所有 spec scenario 要求的可观测终态均保留。
3. **`timed_out` vs `cancelled` 区分**：`agent_loop.run` 因 token 取消是优雅返回（非抛异常），故在其返回后检查 `child.is_cancelled()`；`child.deadline` 已过记 `timed_out`，否则（父/外部触发）记 `cancelled`，与 design D3 一致。
4. **`SubAgentResult` 契约不变**：`timed_out`/`cancelled` 任务 `error` 仍为 None、`result` 为 agent_loop 返回的部分结果；运行态可观测性全部落 `sub_agent_runs` 表（旁路增强），不改批返回语义，既有 `test_sub_agent.py` 不回归。

**遇到的问题与处理：**
- **既有计时测试 `test_tasks_run_concurrently_not_sequentially`**：(a) 该测试原**未隔离 DB**，我新增的持久化会写真实 `data/users.db` → 已加 `monkeypatch DB_PATH` 到 tmp_path 修正隔离；(b) 同步 sqlite 持久化（CLAUDE.md 强制同步、每次 commit 一次 fsync）使并行 elapsed 从 ~0.05 升到 ~0.10，触发原 `elapsed < 0.09` 的过紧代理阈值。处理：先按自解决策 #2 把热路径写入降到最少（init + 每任务 2 写），再把绝对阈值放宽到 `< 0.13`（仍能区分并行 ~0.10 与完全串行 ~0.15+），并加注释说明——**并发性的权威断言是 130-131 行「两任务启动时间差 < 0.02s」**（串行则差 >0.05s），绝对时间只作宽松上限。
- **circular import（预存）**：`sub_agent ↔ agent_loop` 互相 import 导致 `test_sub_agent.py` 无法单独运行（基线即如此），需在全量套件或与 `test_agent_loop.py` 同跑。本 change 未触碰该结构，不修既有问题。

**影响：**
- 新增 `sub_agent_lifecycle.py`、`tests/test_sub_agent_lifecycle.py`（16 测试）；改 `cancellation.py`/`config.py`/`sub_agent.py`、`tests/test_cancellation.py`（+4）/`tests/test_sub_agent.py`（+6 及 1 处既有测试加 DB 隔离 + 阈值放宽）。
- 测试：**全量 `ANTHROPIC_API_KEY=test-key uv run pytest` → 1237 passed，0 失败，零回归**。
- ruff：仅改动文件 format+check 全绿。
- mypy：74 → 75（+1）。该 +1 为 `sub_agent_lifecycle.py:79` 的 `Settings()` call-arg，与 `termination.py:28`、`context_mgr.py:55` 完全同款的**既有错误模式实例**（运行时由 env 提供 `anthropic_api_key`），非新增错误模式，沿用 wave2 先例口径，不以不一致的 inline ignore 抑制。

**需 zy 核实：**
1. 顺序前置 AR20（自解决策 #1）是否认可。
2. 热路径不单独持久化 `pending`、仅在 pre-cancel 分支持久化（自解决策 #2）是否认可——以一次 fsync 换取 pending 态的极短可观测窗口。
3. 既有并发测试阈值由 `0.09` 放宽到 `0.13` + 加 DB 隔离（并发性改由启动重叠断言权威保证）是否认可。
4. mypy +1（既有 `Settings()` 模式实例）是否认可。

---

## tool-timeout（T2）— feat/tool-timeout

**实现：**
- `tool_registry.py`：新增平行元数据 `_timeouts: dict[str, float]` + 模块级常量 `DEFAULT_TOOL_TIMEOUT = 30.0`（可 monkeypatch）；`@tool` 增可选 `timeout: float | None`（写入 `_timeouts`）；`get_timeout(name)`（per-tool 或 None）、`get_effective_timeout(name)`（per-tool 覆盖，否则全局默认）。timeout 是装饰器元数据、非函数参数，天然不进 `_build_schema` 导出的 schema（与 `risk_level`/`connector` 一致）。
- `error_classifier._categorize`：识别 `TimeoutError` → `ErrorCategory.tool_timeout`（接入 AR5 预留码，使其首次可达；`isinstance(error, TimeoutError)` 在 `APIStatusError` 判定前）。
- `agent_loop._safe_dispatch`：解析 `get_effective_timeout(name)`，构造 `child = CancelToken(deadline=now+t, parent=run_cancel_token)` 注入工具（取代直接注入 run 级 token），coroutine 结果经 `asyncio.wait_for(coro, t)` 竞速；超时捕获 `TimeoutError` → `child.cancel()` + 返回 `("tool execution timed out after {t}s", failed=True)`；其余异常仍归一为 `tool execution error`。

**自解决策（针对 design Open Questions）：**
1. **全局默认承载位置**：定为 `tool_registry.DEFAULT_TOOL_TIMEOUT` **模块级常量**（最简、天然可 monkeypatch，满足 spec「默认 30s、可注入/可覆盖」）。**未**新增 `Settings`/settings.yaml 字段——运维 yaml 配置按 design 留作后续（如需，加 `Settings.tool_timeout_seconds` 透传该常量），本 change 不引入。
2. **tool_timeout 归类接入点**：采用 **D2-a**（扩展 `_categorize` 识别 `TimeoutError`），而非 D2-b（工具层读表）。理由：D2-a 使 `classify(TimeoutError())` 直接可达 tool_timeout、最易测且语义单一；`APITimeoutError`（Anthropic SDK 请求超时）非 `TimeoutError` 子类，不会被误归类，无副作用。
3. **per-tool token 经 parent 链接 run 级 token**（design D1 核心）：注入工具的不再是 run 级 token 本身，而是 `CancelToken(deadline, parent=run_token)`，使工具**同时**响应自身超时与 run 级取消。复用 AR20 补全的 `parent` 原语，不另造组合机制。

**遇到的问题与处理：**
- **既有测试 `test_run_threads_token_to_dispatch` 断言注入的是 run 级 token 身份（`is token`）**——该断言对应旧契约。T2 的 design D1 有意改契约（注入带 parent 链接的 child）。已更新该测试：断言注入的是 `CancelToken`、`parent is token`、`deadline is not None`，并新增「`token.cancel()` 后 child `is_cancelled()` 为真」验证 run 级取消仍经 parent 传播到工具——保留测试本意（取消能到达工具）且反映新契约。
- **`sub_agent` 工具不受影响**：它是同步 `def`（非 coroutine），不经 `asyncio.wait_for` 包裹，30s 默认不会误杀其内部 300s 子 agent 批次。`run_code`（async）套 30s 默认符合 tools.md「默认 30s」，非回归。
- **SB7 边界**：本 change 仅做 await 层竞速 + cancel token，**不** `docker kill`；容器侧硬终止留给 SB7。测试以普通 async 工具超时验证 await 层停止 + `tool_timeout` 归类，不涉沙箱。

**影响：**
- 改 `tool_registry.py`/`error_classifier.py`/`agent_loop.py`；新增 `tests/test_tool_timeout.py`（13 测试），`tests/test_error_classifier.py`（+1）、`tests/test_agent_loop.py`（更新 1 既有测试）。
- 测试：**全量 1251 passed，0 失败，零回归**。
- ruff：仅改动文件 format+check 全绿（`agent_loop.py:1008` 的 N814 `CompletionUsage as _CU` 为 HEAD 既有 grandfathered，非本 change 引入，未触碰）。
- mypy：75 → 75，无新增。

**需 zy 核实：**
1. 全局默认用模块常量、未加 Settings/yaml 字段（自解决策 #1）是否认可。
2. 归类接入点 D2-a（扩展 `_categorize`）是否认可。
3. `test_run_threads_token_to_dispatch` 断言由「`is token`」改为「`parent is token` + deadline + 取消传播」是否认可。

---

## tool-result-truncation（T4）— feat/tool-result-truncation

**实现：**
- 新增 `src/fleetent/tool_result_truncation.py`：纯函数 `truncate_tool_result(result, max_bytes=None)` + 模块级 `MAX_TOOL_RESULT_BYTES = 40_000`（~10k tokens，可 monkeypatch）。超阈值时头尾保留 + 中间 breadcrumb `[...工具结果已截断：原始 {orig} 字节，省略中间 {omitted} 字节...]`；字节口径 `len(encode("utf-8"))`（与 SB6 一致）；切点回退到完整 UTF-8 字符边界（`_head_bytes`/`_tail_bytes` 逐字节回退解码），保证合法 UTF-8 且总字节 ≤ 阈值。
- `tool_registry.py`：新增 `_self_truncating: set[str]` + `@tool(self_truncates=False)` 参数 + `is_self_truncating(name)`（平行于 `_risk_levels`/`_timeouts`，不进 schema）。`tools.py` 给 `run_code` 声明 `self_truncates=True`。
- `agent_loop.py`：`run()`（工具消息写回）与 `run_stream()`（写回，SSE 事件仍发原始 result）两处，对非 `self_truncates` 工具的 `result` 在 `messages.append` 前调 `truncate_tool_result`；`dispatch()` 返回值不变（`loop_detector.result_digest`、`tool_result` SSE 事件仍见完整结果）。

**自解决策：**
1. **breadcrumb 预算的轻微循环依赖**：breadcrumb 文本含 `{orig}`/`{omitted}` 数字、其位数影响 breadcrumb 字节长度→影响头尾预算→影响 omitted。解法：用 `omitted ≤ orig`（位数不超 orig）以 `format(orig, omitted=orig)` 作 breadcrumb 长度**上界**预留 `reserve`，再分头尾预算；最终 breadcrumb 实际字节 ≤ reserve，保证 `head+breadcrumb+tail ≤ limit` 恒成立。
2. **`run_code` 经 `self_truncates` 对 T4 豁免**（design D5）：不抬高 T4 默认迁就 sandbox 60KB，不二次截、无双 breadcrumb、无数值耦合——SB6 独占 run_code 截断，T4 管其余工具。
3. **trace 随截断变小**（design D4）：trace 序列化的是已截断的 messages（= LLM 实际所见），不另存完整原文，符合 eval_logger「只记元数据/样本」克制原则；breadcrumb 的原始/省略字节数即审计所需大小元数据。

**影响：**
- 新增 `tool_result_truncation.py`、`tests/test_tool_result_truncation.py`（11 测试）；改 `tool_registry.py`/`tools.py`/`agent_loop.py`、`tests/test_agent_loop.py`（+3 集成测试）。
- 测试：**全量 1265 passed，0 失败，零回归**。
- ruff：我新建/改文件 format+check 全绿；`agent_loop.py:1020` N814（`CompletionUsage as _CU`）与 `tools.py:243` 的 F401/E501（`schedule_task`/`cancel_task`）均为 HEAD 既有 grandfathered（wave2 已记），非本 change 引入，未触碰。
- mypy：75 → 75，无新增。

**需 zy 核实：**
1. T4 默认阈值 40KB（~10k tokens）+ `run_code` 经 `self_truncates` 豁免、SB6 独占（自解决策 #2）是否认可。
2. breadcrumb 中文文案与「原始/省略字节数」格式是否认可。
3. trace 随截断变小、不另存完整原文（自解决策 #3）是否认可。

---

## tool-call-guardrails（AR10）— feat/tool-call-guardrails

**实现：**
- 新增 `src/fleetent/tool_guardrails.py`：`GuardrailAction`（proceed/short_circuit/stop）+ `evaluate_guardrail(state, tool_name, fingerprint, threshold)`：在 `LoopState` 上维护严格背靠背连续计数（相同 `(tool, fingerprint)` +1、相异重置为 1），达阈值且未警告→short_circuit，已警告再来→stop。参数指纹复用 `loop_detector.arg_fingerprint`（与 AR4 同一判定）。
- `termination.py`：`LoopState` 增 `last_call_fingerprint`/`consecutive_repeat`/`guardrail_tripped`（默认值，向后兼容）；新增 `GuardrailChecker`（读 `guardrail_tripped` → `StopReason.loop_detected`，仿 `ApprovalRejectedChecker`，不新增枚举），在 `_build_controller` 注册（approval 之后、loop_checker 之前）。
- `config.py`：`guardrail_repeat_threshold: int = 3`（与 `agent_loop_repeat_threshold` 对齐）。
- `agent_loop.py`：`_resolve_guardrail_threshold`（call > Settings > 默认）；`run()`/`run_stream()` 各加 `guardrail_repeat_threshold` 参数并在循环前解析；两处 tc 循环在 dispatch 前调 `evaluate_guardrail`：非 proceed 则跳过执行、补占位 tool_result（content=`_GUARDRAIL_FEEDBACK_TEXT`）、short_circuit 置 `loop_warning_injected`、stop 置 `guardrail_tripped`，并 `record_tool_call` 后 `continue`。run_stream 同时发 `tool_result` SSE 事件（feedback 文案）。

**自解决策（Q3 已在 design D1 钉死，无遗留 OQ）：**
1. **阈值默认 3**：与 AR4 `agent_loop_repeat_threshold` 对齐，运维只需理解一个"重复次数"直觉值（差异在计数方式：AR4 窗口 vs AR10 严格连续）。
2. **强制停止复用 `StopReason.loop_detected`**：不新增 `guardrail_tripped` 枚举；粒度差异靠 trace 来源元数据区分（design D3）。
3. **首次命中=短路+占位 tool_result**：不走 AR4 的 `_maybe_inject_loop_warning`（per-call 警告由占位 tool_result 承载）；置 `loop_warning_injected` 仅为与 AR4 协调避免重复警告。
4. **接入点=dispatch 前的 tc 循环**：与 design D2 一致；占位 tool_result 保消息序列合法（仿 approval_rejected 不变式）。
5. **stop 经状态 flag + GuardrailChecker 在下个 checkpoint 触发**（而非 tc 循环内直接 break），与终止框架范式一致（should_stop 在轮顶，不会多发 LLM 调用）。

**影响：**
- 新增 `tool_guardrails.py`、`tests/test_tool_guardrails.py`（9 测试）；改 `termination.py`/`config.py`/`agent_loop.py`、`tests/test_agent_loop.py`（+2 集成）。
- 测试：**全量 1276 passed，0 失败，零回归**。
- ruff：我新建/改文件 format+check 全绿（`agent_loop.py:1088` N814 `CompletionUsage as _CU` 为 HEAD 既有 grandfathered，非本 change）。
- mypy：75 → 76（+1）。该 +1 为 `agent_loop.py:147` `_resolve_guardrail_threshold` 的 `Settings()` call-arg，与 `_resolve_loop_config`/`_resolve_budget_config`/`termination._default_config` 完全同款既有模式（运行时 env 提供 key），非新增错误模式。

**需 zy 核实：**
1. 阈值默认 3、与 AR4 对齐、可经 `guardrail_repeat_threshold` 注入（Q3 决策）是否认可。
2. 占位 tool_result 文案 `_GUARDRAIL_FEEDBACK_TEXT`（中文）是否认可。
3. stop 经 `GuardrailChecker` 在下个 checkpoint 归一为 `loop_detected`（自解决策 #2/#5）是否认可。

---

## sandbox-output-truncation（SB6）— feat/sandbox-output-truncation

**实现：**
- 新增 `src/fleetent/sandbox_output_truncation.py`：`truncate_stream(text, max_bytes=None)` + 模块级 `MAX_STDOUT_BYTES = 50*1024`、`MAX_STDERR_BYTES = 10*1024`（可 monkeypatch）。头尾保留 + 中间说明 `[...沙箱输出已截断：原始 {orig} 字节，省略中间 {omitted} 字节...]`，UTF-8 字节口径、多字节安全切分、总字节 ≤ 阈值（与 T4 同形）。
- `tools.py`：`run_code` 拼装前对 `result.stdout` 用 `MAX_STDOUT_BYTES`、`result.stderr` 用 `MAX_STDERR_BYTES` 分别 `truncate_stream`；trace（`log_sandbox_exec`）仍记**原始**字节、`ExecResult` 不改。两流各自独立限额。

**自解决策：**
1. **截断在 run_code 拼装侧、不在 `SandboxClient.exec` 内**（design D1）：exec 是底层原语，其 ExecResult 还供 trace/其它消费者，在 exec 内截断会污染 trace 原始口径、越权。
2. **stdout/stderr 各自阈值**（50KB/10KB，sandbox.md）：两流量级不同，不合并用单一阈值。
3. **run_code 经 `self_truncates` 对 T4 豁免、SB6 独占**（design D3）：T4 时已给 run_code 声明 `self_truncates=True`，本 change 验证该边界（不二次截、无双 breadcrumb、无阈值耦合）。
4. **monkeypatch 友好**：`tools.py` 经 `import sandbox_output_truncation as sot` 在调用时读 `sot.MAX_STDOUT_BYTES`/`sot.MAX_STDERR_BYTES`（而非 `from ... import` 绑定值），使测试 monkeypatch 模块属性即时生效。
5. **trace 记原始字节**（design D4）：返回 AI 的副本截断、trace 记真实规模，二者目标相反分别处理。

**影响：**
- 新增 `sandbox_output_truncation.py`、`tests/test_sandbox_output_truncation.py`（9 测试）；改 `tools.py`、`tests/test_tools.py`（+4 集成）。
- 测试：**全量 1288 passed，0 失败，零回归**。
- ruff：我新建/改文件 format+check 全绿（已修我引入的 import 排序 I001）；`tools.py:249` 的 F401（`cron_scheduler` 未用，在 `schedule_task`）为 HEAD 既有 grandfathered（wave2 已记），非本 change，未触碰。
- mypy：76 → 76，无新增，新模块零错误。

**需 zy 核实：**
1. 截断在 run_code 拼装侧、两流各自阈值 50KB/10KB（自解决策 #1/#2）是否认可。
2. 说明文案（中文）与 trace 记原始字节（自解决策 #5）是否认可。

---

## sandbox-exec-timeout（SB7）— feat/sandbox-exec-timeout

**实现：**
- `sandbox_client.py`：新增 `kill_workspace(id)`（`_docker_kill` SIGTERM → 固定宽限 `_KILL_GRACE_SECONDS=5.0`（可 monkeypatch）→ 无条件 SIGKILL，宽限期内不 `docker inspect` 轮询；非零码 log 警告不崩）+ 模块常量。
- `tools.py`：`_exec_or_cancel` abort 分支改为 `kill_workspace` + `destroy_workspace`；`run_code` 取 `manager.resources_for(scope).exec_timeout`，构造 `child = CancelToken(deadline=start+exec_timeout, parent=token)` 传入轮询（复用 AR20 `parent` 原语合并沙箱 deadline 与外部 token，单 token 判定）；result 为 None 时按 `child.deadline` 是否已过区分：已过→`sandbox_timeout`（读 `_sandbox_timeout_classification()` = AR5 表，log 警告）+ 返回「沙箱执行超时」文本；否则→既有「code execution cancelled」。新增 `_sandbox_timeout_classification()`（镜像 `mcp_client._disconnect_classification`，直接读表）。

**自解决策（重要，需核实）：**
1. **abort 路径 = `kill_workspace` + `destroy_workspace`（kill 后仍 rm），而非纯 kill 替代**：design D2 字面是「kill_workspace 替代 destroy_workspace」。但核实发现 `docker run` **无 `--rm`**、`find_workspace` 只查运行中容器、`run_code` abort 后 `manager.forget` → 若纯 kill（容器停而不删），下次 `acquire` 必 `find` miss → `create_workspace` 撞**停止的同名容器** → RuntimeError（既有 `test_run_code_cancel_forgets_registry_then_reacquires` 即覆盖此重建路径）。故采「kill 优雅终止进程（SB7 新增）+ rm 移除（既有清理，幂等）」：既满足 D2「`docker kill` 序列优雅终止」取代旧的暴力 `rm -f`-as-terminator，又保住 design D2 自述「容器去留沿用 SB2 既有约定（abort 即移除）」、避免撞名回归。**这是对 D2「替代」字面的收敛——以"优雅终止 means 取代暴力 means、移除清理保留"理解，而非"完全不移除"。**
2. **超时 vs 取消区分**：按 `child.deadline` 是否已过（与 AR20 `timed_out` vs `cancelled` 逐字镜像），两路径共用 `kill_workspace`，归类/文本不同。
3. **归类直接读表**（D3 方案 a，镜像 mcp_client）：`sandbox_timeout` 三标志均 False，不新建码、不改语义；接入后该预留码可达。
4. **kill 宽限期=固定等待 + 无条件 SIGKILL**（design D2）：不 `docker inspect` 轮询，对已停容器再 SIGKILL 幂等无害，省 CLI 往返。

**影响：**
- 改 `sandbox_client.py`/`tools.py`；`tests/test_sandbox_client.py`（+2 kill 序列）、`tests/test_tools.py`（+4：分类 + 超时/取消/正常）。
- 测试：**全量 1294 passed，0 失败，零回归**（既有取消测试 `aborts_and_destroys_on_cancel`/`forgets_registry_then_reacquires` 因 kill+destroy 仍 destroy 而继续通过）。
- ruff：我改/建文件 format+check 全绿；`tools.py` 的 F401（`cron_scheduler`，schedule_task）为 HEAD 既有 grandfathered。
- mypy：76 → 76，无新增。

**需 zy 核实：**
1. **（最重要）** abort 路径 kill 后仍 destroy（自解决策 #1）是否认可——纯 kill 会致撞名回归，故保留移除清理；这对 D2「替代」做了"优雅终止取代暴力终止、移除保留"的收敛解释。
2. `_KILL_GRACE_SECONDS=5.0` 固定宽限 + 无条件 SIGKILL（不轮询 inspect）是否认可。
3. 超时文案「沙箱执行超时…」与外部取消文案「code execution cancelled」区分是否认可。

---

## compression-trace（AR16）— feat/compression-trace

**实现：**
- `eval_logger.py`：新增 `log_compression(...)`（`kind: "compression"`，必填 trigger/outcome/前后 token 与消息数/head·tail·dropped 计数/elapsed_s，可选 summary_model/fingerprint/len/user_id/agent_name/session_id「非 None 才写」），复用 `TRACE_PATH` 单一出口与既有写法。
- `context_mgr.py`：`_compress` 增内部参数 `trigger`/`session_id`/`user_id`/`agent_name`；入口采 `t0`/`tokens_before`/`messages_before`；三返回分支（no_middle/degraded/summarized）return 前各采 after 指标 + 调 `_log_compression_safe`（恰好一条 trace）。`maybe_compress`（force→manual / 否则 tmax）与 `compress_for_context_overflow`（context_overflow）透传 trigger + 归因。新增 `_summary_fingerprint`（sha256 前 16 hex，标准库）、`_resolve_summary_model`（复用 `get_client_and_config("memory_extraction").model`，防御式 try/except→None）、`_log_compression_safe`（try/except 包裹，写失败仅 warning）。
- `agent_loop.py`：run/run_stream 两处 `maybe_compress(...)` 传入 `session_id`/`user_id`/`agent_name`。

**自解决策：**
1. **`summary_model` 经 `get_client_and_config` 复用解析、不改 `_summarize` 签名**（design D4），并加防御 try/except（可观测性不得破坏压缩）。
2. **摘要只记指纹 + 长度、绝不落正文**（design D2），用 sha256 前 16 hex。
3. **写失败不破坏压缩**（design D5）：`_log_compression_safe` try/except + warning。
4. **dropped_count = len(middle)**（被压缩/丢弃的中段消息数）；no_middle 分支为 0。

**遇到的问题与处理：**
- **既有 context_mgr 压缩测试未隔离 TRACE_PATH**：`_compress` 现写 trace 会触碰真实 `data/`（违反 CLAUDE.md）。处理：给 `test_context_mgr.py` 加 **autouse fixture** 统一把 `eval_logger.TRACE_PATH` 隔离到 tmp_path，一处覆盖全文件。
- **`maybe_compress` 新增可选 kwargs 后，agent_loop 带 kwargs 调用，致 11+2 处测试 mock（旧位置参数签名 `lambda msgs:` / `def recording_compress(msgs)`）抛 TypeError**：真实函数向后兼容（kwargs 默认 None），仅 mock 替身需接受新 kwargs。已给全部 mock 加 `**kw`。这是 mock 签名跟进，非掩盖 bug。

**影响：**
- 改 `eval_logger.py`/`context_mgr.py`/`agent_loop.py`；`tests/test_eval_logger.py`（+3）、`tests/test_context_mgr.py`（+7 及 autouse 隔离 fixture）、`tests/test_agent_loop.py`（13 处 compress mock 加 `**kw`）。
- 测试：**全量 1304 passed，0 失败，零回归**。
- ruff：我改/建文件 format+check 全绿（`agent_loop.py` N814 `CompletionUsage as _CU` 为 HEAD 既有 grandfathered）。
- mypy：76 → 76，无新增。

**需 zy 核实：**
1. 摘要仅记 sha256 前 16 hex 指纹 + 长度、不落正文（自解决策 #2）是否认可。
2. `summary_model` 经路由复用解析 + 防御 try/except（自解决策 #1）是否认可。
3. 给 `test_context_mgr.py` 加 autouse TRACE_PATH 隔离、给 13 处 compress mock 加 `**kw` 是否认可。

---

## compression-anti-flap（AR17）— feat/compression-anti-flap

**实现：**
- `config.py`：`context_flap_window=3`/`context_min_savings_ratio=0.10`/`context_min_interval_turns=1`；`context_mgr._default_config()` 注入三键。
- `context_mgr.py`：`AntiFlapState`（dataclass：recent_savings 元组滑窗 / turns_since_last_compress / auto_disabled）；`apply_anti_flap(messages, state, config, *, attribution) -> (messages, new_state)`（自动门控：熔断或未越线→advance turns；最小间隔未满→skip；否则 `_compress` + 算节省率 + 滑窗 + 连续低节省熔断告警；functional `replace`，不就地改写）；`init_anti_flap_db`/`load_anti_flap_state`/`save_anti_flap_state`（`users.db` 姊妹表 `session_anti_flap` keyed by session_id，标准库 sqlite3，DB_PATH 可 monkeypatch）。
- `agent_loop.py`：`_load_flap_state`/`_save_flap_state`（防御式，DB 失败降级不崩 run）、`_gated_compress`（有 session 状态→apply_anti_flap，否则 maybe_compress=AR12）；run/run_stream 在 run 边界 load（开始）/save（log_run 前），逐 turn 经 `_gated_compress` 透传回收 `flap_state`。

**自解决策（重要，需核实）：**
1. **新增 `apply_anti_flap` 专用函数承载门控路径，`maybe_compress` 保持不变**（而非给 maybe_compress 加 state 参数返 union）。理由：state 传入则需返回 (messages, state)，会把 maybe_compress 的 `list→list` 契约变成 union，破坏既有全部调用方/测试与 mypy（需 overload gymnastics）。专用函数零风险、干净 tuple；force/overflow 不走它即天然满足 D4 豁免。spec scenarios 是行为性的（"自动压缩入口"），由 maybe_compress(state 无=AR12) + apply_anti_flap(门控) 两函数共同满足，未违反任何 spec 要求。
2. **最小间隔判定用 increment-first**：`advanced = turns+1`；`advanced < min_interval → skip`。使默认 `min_interval=1` 时首次越线即压缩（保 AR12 首压行为），`min_interval≥2` 才产生真实间隔。
3. **持久化用姊妹表 `session_anti_flap`**（而非给 session-metadata-index 的 `sessions` 表加列），keeps 该 change schema/语义不动；recent_savings 以 JSON 存。
4. **gating 仅在 session_id 存在时激活**（CLI 无 session→None→AR12 原样），故既有 agent_loop 测试（均不传 session_id）零影响。
5. **熔断为结构化告警 + 状态标志、不抛异常**（D5）。

**影响：**
- 改 `config.py`/`context_mgr.py`/`agent_loop.py`；`tests/test_context_mgr.py`（+12 含持久化/熔断/间隔/跨run）、`tests/test_agent_loop.py`（+2 边界 load/save）。
- 测试：**全量 1318 passed，0 失败，零回归**。
- ruff：我改/建文件 format+check 全绿（`agent_loop.py` N814 grandfathered）。
- mypy：76 → 76，无新增（`context_mgr.py:65` 的 `Settings()` 为 `_default_config` 既有调用，非本 change 引入）。

**需 zy 核实：**
1. **（最重要）** 新增 `apply_anti_flap` 专用函数而非改 `maybe_compress` 签名返 union（自解决策 #1）是否认可——这是对 design「maybe_compress 新增 state 入参」字面的收敛（保契约/类型/兼容）。
2. 最小间隔 increment-first 语义（默认 1 → 首压即时、无间隔，靠熔断兜底）（自解决策 #2）是否认可。
3. 持久化用姊妹表 `session_anti_flap`（自解决策 #3）是否认可；session 删除/过期时的清理本 change 未挂（design Open Question，留后续）。

---

## mcp-degradation（MCP4）— feat/mcp-degradation

**实现：**
- `mcp_client.py`：`is_server_available(server)`（连接 healthy AND 非 oauth2-认证不可用，D1）；`McpServerConfig.degrade_mode: str = "degrade"` + `__post_init__` 经 `_validate_degrade_mode` 校验非法值回退 degrade（log，不静默）；`_schema_visibility(tool_name)`（解析 `{server_id}__{tool}`、查 `_server_registry`、调 is_server_available；非 MCP/未知 server→True）；`install_schema_filter()`（把谓词注入 tool_registry）；`unavailable_strict_server_ids()`（注册的 strict+不可用 ∪ 启动失败的 strict）；`register_all` 清空 `_failed_strict_servers`、strict 启动失败入该集合、末尾 `install_schema_filter()`。
- `tool_registry.py`：可注入 `_schema_visibility_filter`（默认 None=不过滤）+ `set_schema_visibility_filter`；`get_schemas()` 按谓词过滤（过滤视图，不删 `_registry`）。

**自解决策：**
1. **过滤经可注入钩子**（D4）避免分层倒置：tool_registry 只认谓词，MCP 细节留 mcp_client；默认 None 保证非 MCP/既有零回归。
2. **摘除=过滤视图、不删注册项**（D2）：恢复（健康 reset / 认证清除）= 谓词翻真，工具自动重现，无需重注册。
3. **strict 启动失败用 `_failed_strict_servers` 跟踪**（D5）：未注册的 strict server 也纳入 strict 查询；与 `_server_registry` 同属进程级 registry 域（非任意全局可变态），register_all 每次清空重算。
4. **strict 仅暴露判定入口 `unavailable_strict_server_ids()`，不改 agent_loop**（任务 4.6/D3）：agent_loop 据 agent 的 allowed_tools 与 `{id}__*` 命名空间相交决定终止，属后续集成，本 change 不动 agent_loop。
5. **silent 当前等同 degrade**（通知通道未落地，design 前向声明）。

**影响：**
- 改 `mcp_client.py`/`tool_registry.py`；新增 `tests/test_mcp_degradation.py`（16 测试）。
- 测试：**全量 1334 passed，0 失败，零回归**。
- ruff：我改/建文件 format+check 全绿。
- mypy：76 → 76，无新增。

**需 zy 核实：**
1. strict 仅暴露 `unavailable_strict_server_ids()` 判定、agent_loop 集成留后续（自解决策 #4）是否认可。
2. strict 启动失败用进程级 `_failed_strict_servers` 跟踪（自解决策 #3）是否认可。
3. silent 暂等同 degrade（通知通道未实现）是否认可。

---

## scheduled-task-session-binding（S3）— feat/scheduled-task-session-binding

**实现：**
- `schedule_store.py`：`scheduled_tasks` 加可空列 `session_id TEXT`；`create` 增可选参数 `session_id: str | None = None`（写入 + 纳入返回字典）；`list_tasks` 经 `SELECT *` 自动带出。
- `cron_scheduler.py`：`load_cron_yaml` 增 `"session_id": entry.get("session_id")` 映射；`_fire` 重写：`sid = task.get("session_id") or f"cron/{task['id']}/{uuid4().hex}"`，在 `session_mgr.session_lock(sid)` 下 `load` → `messages=[*history, user]` → `_agent_run` → 追加 assistant reply → `save(sid, messages, user_id, agent_name)`。

**自解决策：**
1. **传副本给 `agent_loop.run`、reply 只手动 append 一次**：`agent_loop.run` 原地改传入的 messages（追加 assistant turns），若直接传 `messages` 再手动 append reply 会**重复**最终 assistant 消息。故 `_agent_run(list(messages), ...)`（副本），把 reply append 到 `_fire` 自己的 `messages` 再 save——dup-free，且与 mock（不改 messages）兼容。session 持久化 user + 最终 reply 两条会话轮（不落工具脚手架），干净可观测。
2. **默认独立语义（session_id NULL）**（design D1）：与现状零行为变化、无泄漏；固定复用需显式配 session_id。
3. **统一走 session_lock**（D3）：固定语义防并发覆盖；独立语义每次 sid 不同等价无竞争，代码单一。

**影响：**
- 改 `schedule_store.py`/`cron_scheduler.py`；新增 `tests/test_scheduled_task_session_binding.py`（6 测试）。
- 测试：**全量 1340 passed，0 失败，零回归**。
- ruff：我编辑的两文件 `ruff format` 顺手修了 2 个**预存** E501（基线 8 错→6 错），**零新增**；剩余 6 个（F401 `asyncio` 局部导入、F811 `DB_PATH` 重定义、I001 import 排序）均为 HEAD 既有 grandfathered（stash 对比基线确认），未触碰其所在行。
- mypy：76 → 76，无新增。

**需 zy 核实：**
1. `_fire` 传副本给 run + reply 手动 append（自解决策 #1）是否认可——避免 run 原地改 messages 致 assistant 重复；session 仅持久化 user+最终 reply。
2. 默认独立语义、固定复用需显式配 `session_id`（D1）是否认可。
3. 旧库升级加列 `session_id TEXT` 由 db-migration 走 ALTER TABLE（design D4）——本 change 未含迁移脚本，按既有迁移能力处理。

---

## cost-budget-control（AR18）— feat/cost-budget-control

**实现：**
- 新模块 `layered_budget.py`：`BudgetScope`（task/session/user/agent/global）+ `SCOPE_ORDER`/`CROSS_RUN_SCOPES`；`ScopeUsage`（turns/tokens/cost_usd + `add(prompt,completion,model)`）；`ScopeBudget`（max_turns/tokens/cost_usd，NO_LIMIT 默认，`exhausted_dimension` turns→tokens→cost）；`MODEL_PRICING`/`DEFAULT_PRICING`（每 token USD）；`LayeredBudgetConfig`（per_scope + `from_settings` + `has_any_cap`）；`BudgetWindow`（lifetime/daily/weekly/monthly）+ `period_for`；`BudgetStore`（`users.db` 表 `budget_usage(scope,key,period PK)`，`add`/`get`，task 拒绝，可注入 clock/DB_PATH，跨周期涌现式重置）；`LayeredBudgetChecker`（4 跨运行层由窄到宽，key 缺失跳过，记 triggered_scope/dimension）；`BudgetHeadroom` + `headroom()`。
- `config.py`：12 个跨运行层上限字段（默认 NO_LIMIT）+ 3 个窗口字段。
- `eval_logger.py`：`log_run` 加可选 `budget_scope`。
- `agent_loop.py`：`_setup_layered_budget`（无 cap → 休眠：不注册 checker、不写 DB）、`_layered_budget_add`；run/run_stream 注册 LayeredBudgetChecker、每轮 store.add（与 AR2 `_budget_add` 并存）、budget_exceeded 时 log `budget_scope`。

**自解决策（最重要，务必核实）：**
1. **不碰 `budget.py`，cost 机制全在 `layered_budget.py`**：AR18 的 spec/tasks 假设 cost 维度在 AR2 `budget.py`（`max_cost_usd`/`MODEL_PRICING`/`add(model)`），**但实际 cost 是 AR2 review 主动删除的**——`budget.py` 有 3 个守卫测试（`test_budget_config_has_no_cost_dimension`/`..._usage_...`/`..._no_pricing_tables`）断言其无 cost/pricing。故**不重新给 budget.py 加 cost**（会破坏 review 决定 + 3 个守卫测试），改为 AR18 自有模块实现完整 cost 机制，复用 AR2 的 `NO_LIMIT` 与 turns/tokens 语义（`ScopeUsage.add` 的 turns/tokens 与 `BudgetUsage.add` 同输入同结果，仅多 cost 维度）。AR2 边界测试全绿、五层成本预算照常落地。
2. **默认休眠**：`has_any_cap()` 为假（所有层 NO_LIMIT，默认）时完全不启用——不注册 checker、不写 `budget_usage` 表，既有 agent_loop 测试（默认 Settings、无 cap）零影响、不触碰 `data/`。仅运维显式配置上限才激活。
3. **task 层不落盘**：task 是 per-run（AR2 管），`BudgetStore.add(task,...)` 抛 `ValueError`；只 session/user/agent/global 跨运行持久化。
4. **触发归一为 AR2 `budget_exceeded` → Grace Call**：层级超限复用既有收尾路径，额外经 `log_run(budget_scope=...)` 记录触发层级。

**影响：**
- 新增 `layered_budget.py`、`tests/test_layered_budget.py`（20 测试）；改 `config.py`/`eval_logger.py`/`agent_loop.py`、`tests/test_agent_loop.py`（+1 接线测试）。
- 测试：**全量 1361 passed，0 失败，零回归**（AR2 budget 守卫测试全绿）。
- ruff：我改/建文件 format+check 全绿（`agent_loop.py` N814 grandfathered）。
- mypy：76 → 77（+1）。该 +1 为 `layered_budget.py:146` `from_settings` 的 `Settings()` call-arg，与全仓既有 `_default_config`/`_resolve_*` 同款模式，非新增错误模式。

**需 zy 核实：**
1. **（最重要）** 不复活 `budget.py` 的 cost（被 review 删除 + 守卫），改在 `layered_budget.py` 自实现 cost（自解决策 #1）是否认可——这是对 AR18 spec「复用 AR2 cost」前提的修正。
2. `MODEL_PRICING` 占位单价（claude/gpt 每 token USD）是否需按实际定价校准。
3. 各层默认窗口（session=lifetime / user·agent=weekly / global=monthly）与默认休眠（无 cap 不启用）是否认可。
4. `headroom()` 只读快照已实现但 agent_loop 尚未消费（供上层/后续提示用）——是否认可留作 API/提示后续接入。

---

## cost-aware-routing（MR2）— feat/cost-aware-routing

**实现：**
- 新模块 `cost_aware_routing.py`：从 AR18 import `BudgetHeadroom`（仅消费标量，不重定义）；`CostAction`（normal/degrade）；`CostAwareRoutingPolicy`（`enabled`/`degrade_below`/`degrade_target`，`decide(headroom)` 两档：禁用/headroom=None/无 target → normal，剩余 < 阈值 → degrade）+ `from_settings`；`resolve_base_route(routes, task_type, headroom, policy)`（degrade → `routes.get(degrade_target, default)`，未知 target 回退 default + log；normal → 原 `routes.get(task_type, default)`）。duck-typed routes dict，不 import model_router（无环）。
- `model_router.py`：`get_(async_)client_and_config` 加可选 kwarg `headroom`/`policy`；新增 `_resolve_base`：`headroom is None` → 原 `routes.get(task_type, default)`（**逐字节等价、且不 import cost_aware_routing**），否则经 `resolve_base_route` 降级；override 在 `_apply_override` 中**后于**降级合并（优先级最高）。
- `config.py`：`cost_aware_routing_enabled=False` / `cost_aware_degrade_below=0.2` / `cost_aware_degrade_target=""`（默认整链不干预）。

**自解决策：**
1. **`degrade_target` 默认 None → degrade 不可用**（design D2）：避免「开关一开复杂任务悄悄降到便宜模型」的质量悬崖；只有显式配 target 才降级。
2. **headroom=None 路径零 import、逐字节等价**：`_resolve_base` 在 None 时直接走原查表，连 cost_aware_routing 都不 import，保证所有既有 model_router 调用方零回归。
3. **不设「重排 fallback 优先低价」中间档**（design D5）：fallback 仅主模型失败时用、常态不省钱且会扭曲可靠性序；v1.0 只 normal/degrade 两档，不读单价表。
4. **降级走 task_type 查表、不写死便宜模型名**（D3）：复用既有 `routes.get` + override 合并，不污染 model_router 类型。

**影响：**
- 新增 `cost_aware_routing.py`、`tests/test_cost_aware_routing.py`（14 测试）；改 `model_router.py`/`config.py`。
- 测试：**全量 1375 passed，0 失败，零回归**。
- ruff：我改/建文件 format+check 全绿。
- mypy：77 → 78（+1）。该 +1 为 `cost_aware_routing.py:53` `from_settings` 的 `Settings()` call-arg，与全仓既有模式同款，非新增错误模式。

**需 zy 核实：**
1. `degrade_target` 默认 None、未配则 degrade 不启用（自解决策 #1）是否认可。
2. 默认 `degrade_below=0.2` 阈值是否合适。
3. headroom 由 agent_loop 调 AR18 `headroom()` 取标量后透传给 `get_(async_)client_and_config` 的接线——**本 change 仅落地 model_router 接入点与 policy，agent_loop 实际透传 headroom 的接线属后续**（与 AR18 headroom 的消费端对齐）。是否认可此分界。

---

---

## 评审后修订（2026-06-02，zy 复核决定）

zy 复核全部 13 个 change 后，对 cost 维度做出整体决策：**cost 统计无实际意义，删除该功能**。据此回退：

### 修订 1 — AR18 删除 cost 维度，仅保留 turns/tokens 五层预算
- `layered_budget.py`：移除 `ScopeUsage.cost_usd`、`ScopeBudget.max_cost_usd`、`MODEL_PRICING`/`DEFAULT_PRICING`/`_price`、`add()` 的 `model` 参数、`exhausted_dimension` 的 cost 分支、`BudgetHeadroom`、`headroom()`、`_scope_keys`；`budget_usage` 表去掉 `cost_usd` 列。**保留**五层 turns/tokens 预算、BudgetStore、窗口、LayeredBudgetChecker（用量分层预算独立成立）。
- `config.py`：移除 4 个 `agent_budget_*_cost_usd` 字段（保留 turns/tokens 上限与窗口字段）。
- `agent_loop.py`：`_layered_budget_add` 去掉 `model` 参数（仅累计 turns/tokens）。`budget_scope` 日志字段保留（仍标注触发的 turns/tokens 层级）。
- 主 spec `openspec/specs/agent-cost-budget/spec.md`：重写为 turns/tokens 版，Purpose 注明 cost 经评审移除；删除「暴露预算剩余只读快照」（headroom）整条 Requirement。
- AR2 `budget.py` 始终未被触碰（其 cost 维度本就被 review 删除并有守卫测试，与本次决定一致）。

### 修订 2 — MR2（cost-aware-routing）整体删除/回退
- MR2 100% 靠 cost 剩余（headroom）触发降级；cost 删除后无任何输入信号，故整体回退。
- 删除 `src/fleetent/cost_aware_routing.py`、`tests/test_cost_aware_routing.py`、主 spec `openspec/specs/cost-aware-routing/`。
- `model_router.py`：`get_(async_)client_and_config` 回退到 pre-MR2（移除 `headroom`/`policy` 入参、`_resolve_base`、TYPE_CHECKING import），路由逐字节回到 MR2 前。
- `config.py`：移除 `cost_aware_routing_enabled`/`cost_aware_degrade_below`/`cost_aware_degrade_target`。
- 归档目录 `changes/archive/2026-06-01-cost-aware-routing/` 作为历史保留，但其能力已撤销（主 spec 已删）。

### 连带说明
- q2（headroom 透传后续接线）与 q3（占位单价/阈值）随 cost 删除一并失效，无需处理。
- 影响：**全量 `ANTHROPIC_API_KEY=test-key uv run pytest` → 1357 passed，0 失败**（删 MR2 14 测试 + AR18 cost 测试若干）。ruff 全绿（仅 `agent_loop.py` N814 grandfathered）。mypy 77（= 基线 76 + `layered_budget.from_settings` 的 `Settings()` call-arg 既有模式）。
- 其余 11 个 change 及 AR18 的 turns/tokens 五层预算保持不变，均已 zy 认可。

---

## 复核逐条结论（2026-06-02，zy 逐条过）

> zy 决定逐条复核所有「需 zy 核实」项。本节记录每条结论；认可者保持不变，需改者记改动。

### T3 tool-arg-sanitization
- ① 占位符 `[REDACTED]`：**认可，保持**。
- ② 加 entry 级「曾脱敏」布尔标记：**改——已实现**。`eval_logger` 新增 `_has_redacted_tool_calls`，`log_run`/`log` 在检测到敏感名 tool_call 参数时写 `secrets_redacted: true`（仅 True 才写、不落值），审计可知"曾出现敏感参数"。+3 测试。
- ③ 仅脱敏顶层键、不递归：**认可，保持**。

### AR20 sub-agent-lifecycle
- ① 顺序提前到 #2：**认可，保持**。
- ② 正常路径不单独持久化 `pending`（省一次落盘）：**认可，保持**。
- ③ 并发测试阈值 0.09→0.13（并发性由启动时间差<0.02s 权威保证）：**认可，保持**。
- ④ mypy +1（`Settings()` 既有模式）：**认可，保持**。

### T2 tool-timeout
- ① 全局默认超时承载：**改——已加配置开关**。新增 `Settings.tool_default_timeout_seconds=30.0`；`agent_loop` 每次运行经 `_resolve_default_tool_timeout()` 读一次、下传给 `_safe_dispatch` → `get_effective_timeout(name, default)`；单工具 `@tool(timeout=)` 仍可覆盖。+3 测试。
- ② 超时归到已有 `tool_timeout` 类别（扩展 `_categorize` 认 `TimeoutError`）：**认可，保持**。
- ③ 唯一改既有测试（注入 token 由"run token 本身"变"连着自身超时+run 取消的新 token"）：**认可，保持**。

### T4 tool-result-truncation
- ① 默认 40KB + run_code 经 self_truncates 豁免、SB6 独占：**认可，保持**。
- ② 截断中文说明文案：**认可，保持**。
- ③ 存档记截断后内容、不另存原文：**认可，保持**。

### AR10 tool-call-guardrails
- ① 重复阈值默认 3、与 AR4 对齐、可配：**认可，保持**。
- ② 跳过提示中文文案：**认可，保持**。
- ③ 停止归 `loop_detected`、不新造枚举：**认可，保持**。

### SB6 sandbox-output-truncation
- ① stdout 50KB / stderr 10KB 各自阈值：**认可，保持**。
- ② 中文说明 + 存档记原始字节：**认可，保持**。

### SB7 sandbox-exec-timeout
- ① abort 路径 kill 后仍 destroy（防撞名回归）：**认可，保持**。
- ② 固定宽限 5 秒 + 无条件 SIGKILL（不轮询 inspect）：**认可，保持**。
- ③ 超时/取消文案区分：**认可，保持**。

### AR16 compression-trace
- ① 摘要仅记 sha256 前16hex 指纹 + 长度、不落正文：**认可，保持**。
- ② `summary_model` 防御式解析（出错记空）：**认可，保持**。
- ③ 测试加 autouse TRACE_PATH 隔离 + 13 处 compress mock 加 `**kw`：**认可，保持**。

### AR17 compression-anti-flap
- ① 新增 `apply_anti_flap` 专用函数、不改 `maybe_compress` 返 union：**认可，保持**。
- ② 最小间隔默认 1（首压即时、之后不强制隔开，主靠熔断）：**认可，保持**。
- ③ 姊妹表 `session_anti_flap` + 过期清理留后续：**认可，保持**。

### MCP4 mcp-degradation
- ① strict 集成：**改——现在就接通 strict 停机**（agent_loop：agent 绑定了 strict-且-不可用服务时以明确错误终止）。
- ② strict 启动失败用进程级集合跟踪：**认可，保持**。
- ③ silent vs degrade：**改——现在就做区别**（无通知通道下，用日志级别区分：degrade=warning 显著、silent=debug 安静）。

### S3 scheduled-task-session-binding
- ① `_fire` 存什么：**改——存完整对话**。不再传副本+手动追加 reply，而是把真实消息列表交给 `run`（就地补全 user+工具调用步骤+最终回复），直接 `save` 整个列表；下次固定 session 触发能看到完整上下文（含工具步骤）。测试 mock 改为模拟"run 就地追加"。
- ② 默认独立 session 语义、固定复用需显式配 `session_id`：**认可，保持**。
- ③ 旧库加列 `session_id` 的迁移脚本：**保持现状——不补**（新装库建表即带该列；旧库该列靠后续/其他机制，本 change 不写迁移脚本）。
