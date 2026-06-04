## Context

`_safe_dispatch`（`agent_loop.py` 行 185-214）是主循环执行工具的唯一边界：它调用 `dispatch`，若返回 coroutine 就 `await`，并把异常归一为 `(error_text, failed=True)` 让循环不被工具崩溃杀死。但它**没有时限**——卡住的工具会让主循环在 `await result` 上无限阻塞。

AR19（`cancellation.py`，已合入）已发布 cancel token 契约：`CancelToken(deadline: float | None)`，`is_cancelled()` 合并「显式 `cancel()`」与「`time.monotonic() >= deadline`」两个出口；docstring 明文「a timeout is just `CancelToken(deadline=now + timeout)`」「This module defines the contract wave-3 timeout features (T2 / SB7) reuse」。`dispatch`/`_safe_dispatch` 已支持把 token 注入**声明接受** `cancel_token` 参数的工具（out-of-band，不进 schema）。`run()`/`run_stream()` 已为每次运行构造一个 `CancelToken()` 并贯穿调度。

AR5（`error_classifier.py`，已归档）的 `CLASSIFICATION_TABLE` 已含 `ErrorCategory.tool_timeout` 及其标志位（`_entry(tool_timeout)`，三标志均 False），但 `_categorize()` 只识别 `APIStatusError`，其余落 `unknown`——`tool_timeout` 是**预留码**，按 AR5「预留分类码不被主动返回」尚不可达。本 change 是接入该错误源的功能。

约束（CLAUDE.md）：禁止 AI 框架；禁止 ORM（标准库 sqlite3，本 change 不涉数据库）；禁止全局可变状态（超时默认值/全局配置项以模块级常量承载，可 monkeypatch 注入）；新模块/扩展遵循 import → 常量 → 数据类 → 函数；mypy strict 全注解；行长 100；TDD Hard Gate；测试 mock LLM、异步超时用可控方式（注入极短超时或可控慢工具 stub，不真实长 sleep）、隔离 tmp_path/monkeypatch；不吞异常（超时要归一为错误文本返回，而非静默）。

## Goals / Non-Goals

**Goals:**
- 为单次工具调用施加超时保护：超过配置时限即停止等待，主循环不被卡死的工具阻塞。
- 复用 AR19 `CancelToken(deadline=now+timeout)` 作为超时的**统一机制**（不另造超时原语）；超时到点 `cancel()` token，使声明接受 token 的工具能协作式停止。
- 超时归一为 `tool_timeout` 错误（接 AR5 预留码），以错误文本经 `_safe_dispatch` 的 `(text, failed=True)` 约定返回给 LLM。
- 时限可配置：全局默认（30s）+ per-tool 覆盖（`@tool(timeout=...)`）；默认值与全局项可注入（模块级常量，可 monkeypatch）。

**Non-Goals:**
- 不实现 `docker kill`（SIGTERM→SIGKILL）容器强制终止——那是 SB7（沙箱执行超时）的特化职责（见「与 SB7 边界」）。
- 不改 AR19 token 接口（仅新增「构造带 deadline 的 token」用法）。
- 不改 AR5 分类表结构（仅令 `tool_timeout` 预留码首次可达）。
- 不实现工具结果截断、参数消毒（tools.md 同段的另两项规划，各自独立）。
- 不改未超时工具调用的行为（兼容现状）。

## 与 SB7（沙箱执行超时）边界

T2 与 SB7 都源自 AR19 的同一 token 契约，但**层级与中止手段不同**，本 change 明确划界：

| 维度 | T2（本 change，tool-timeout） | SB7（sandbox 执行超时） |
| --- | --- | --- |
| 层级 | **工具层通用**：任意工具（IO/外部进程/MCP/run_code）的单次调用 | **沙箱内特化**：仅 `run_code` 在 Docker 容器内执行 |
| 时限来源 | 全局默认 + `@tool(timeout=...)` per-tool 覆盖 | 沙箱资源配置的 `exec_timeout`（SB3/资源配置承载，见 `sandbox-resource-limits`） |
| 中止手段 | asyncio await 层竞速 + `cancel()` token（协作式停止，停止等待） | 对容器 `docker kill`（SIGTERM，5s 后 SIGKILL）**强制终止**并清理 |
| 归类 | `tool_timeout` | `sandbox_timeout`（AR5 另一预留码） |

T2 是「工具层不被卡死」的通用兜底；SB7 是「沙箱容器内代码真正被杀掉、容器被清理」的特化。一次 `run_code` 超时在概念上可同时被两层覆盖：SB7 负责容器侧的硬终止，T2 负责 await 层不阻塞与归类。本 change **只做 T2**，不触碰 `docker kill`，也不消费 `exec_timeout`（那是 sandbox 侧配置）。

## Decisions

### D1：超时施加在 `_safe_dispatch` 的 await 边界，竞速 + cancel token（经 `parent` 链接合并 run 级取消）
在 `_safe_dispatch` 内为本次工具执行解析有效超时 `t`（见 D3），构造 `child = CancelToken(deadline=now + t, parent=run_cancel_token)` 注入给声明接受 token 的工具，并在 asyncio await 层把工具执行与超时竞速（如 `asyncio.wait_for(coro, timeout=t)` 或等价的 deadline 竞速）。到点：`cancel()` 该 child token（让协作式工具尽快停止），停止等待，归一为 `tool_timeout` 错误返回。

**双取消源经 `parent` 合并**：`run()`/`run_stream()` 已为每次运行构造一个 run 级 `cancel_token` 并注入声明接受它的工具（用户取消整个会话时由此 token 传播）。T2 现在要再给单次工具一个 per-tool deadline token——若只「构造 `CancelToken(deadline=now+t)` 并注入」，会把 run 级 token 顶掉/旁路，该工具就**只看自己的超时、收不到 run 级取消**。故 per-tool token MUST 经 `parent=run_cancel_token` 链接挂接 run 级 token：`child.is_cancelled()` 在「自身 `_cancelled` / 自身 deadline 已过」之外再 OR 上 `parent.is_cancelled()`，使工具**同时**响应「自己超时（deadline）」与「run 级取消（parent）」两个源。该 `parent` 链接原语由 `sub-agent-lifecycle`(AR20，D3/②) 对 `cancellation.py` 的 `CancelToken` 增量补全（可选 `parent` 字段、纯加法、向后兼容），本 change 作为消费方**复用**该原语，不另造组合机制。

**asyncio.wait_for 语义**：`asyncio.wait_for(coro, t)` 超时时会**向 coro 抛 `CancelledError` 并等其取消**——纯异步工具在下一个 await 点 unwind（并非「后台继续跑」）；只有工具 spawn 的**外部 OS 进程/容器**（docker、subprocess）不被该 asyncio 取消杀掉，这才是 SB7（`docker kill`）存在的理由（见 D4 / 「与 SB7 边界」）。`_safe_dispatch` 捕获的是 `wait_for` 抛给调用方的 `TimeoutError`（而非 coro 内部的 `CancelledError`），据此走 `(error_text, failed=True)` 归一与 `tool_timeout` 归类（见 D2）。

**为何**：`_safe_dispatch` 是工具执行的唯一边界，已持有 token 注入与异常归一逻辑，超时与它们同处一点最自然，不必侵入每个工具。竞速保证「即使工具完全不查 token（不协作）」主循环也能停止等待——cancel token 是协作式信号，单靠它无法中止不查 token 的工具，故 await 层竞速是**不阻塞的硬保证**，cancel token 是**让协作式工具优雅退出**的叠加。
**Alternatives**：①只靠 cancel token 不竞速——被否，不查 token 的工具仍会阻塞主循环，达不到「不卡死」目标；②给每个工具内部加超时——被否，侵入性强、易漏，违反「调度边界统一兜底」；③用线程池 + 超时杀线程——被否，Python 无法安全杀线程，且与既有 async 模型冲突；④为本次工具构造独立 deadline token **不挂 `parent`**——被否，会把 run 级 token 顶掉/旁路，工具收不到 run 级取消传播（用户取消整个会话时在途工具无感知）。

### D2：超时归一为 `tool_timeout`（接入 AR5 预留码）
超时竞速触发的异常（`asyncio.TimeoutError`，即 `TimeoutError`）在工具层被归类为 `ErrorCategory.tool_timeout`，复用 AR5 `CLASSIFICATION_TABLE` 中已存在的该条目与标志位（三标志均 False：超时不自动重试/压缩/切模型，交由 LLM 决定下一步）。返回给 LLM 的文本明确指出是工具超时（区别于 `tool_crash`）。

**接入点**（实现时二选一，spec 不绑定具体形态，只约束可观察行为）：
- (a) 扩展 `error_classifier._categorize`：识别 `TimeoutError` → `tool_timeout`，使 `classify()` 直接可达该码；
- (b) 工具层在 `_safe_dispatch` 直接映射超时为 `tool_timeout`（读 `CLASSIFICATION_TABLE[tool_timeout]` 取标志位），不经 `classify()`——与 `mcp_client._disconnect_classification()` 既有做法一致（该处直接读表、不调 `classify()`）。

**为何**：AR5 已把 `tool_timeout` 及标志位定义为单一事实来源，本 change 是其「错误源接入」，不应另立分类码或重定义标志位。三标志为 False 符合 AR5 既有条目语义（超时是工具侧问题，盲目重试同一工具无益，让模型据错误文本决策）。
**Alternatives**：①新建独立超时错误码——被否，与 AR5 预留码重复，违反单一事实来源；②超时即 `should_retry=True` 自动重试——被否，会改 AR5 既有标志位语义且可能放大卡顿，超出本 change 范围。
**与 AR5 spec 的关系**：AR5「预留分类码不被主动返回」要求「未接入对应错误源前」`classify()` 不返回预留码——本 change **正是**该接入；故本 change 后 `tool_timeout` 可达，不与 AR5 spec 冲突（AR5 的限定语正为本 change 留口）。

### D3：超时时限解析——per-tool 覆盖全局默认，全部可注入
- `@tool(timeout: float | None = None)`：可选 per-tool 时限（秒），记录到 `tool_registry` 中与 `_risk_levels`/`_connectors` 平行的元数据表；`get_timeout(name) -> float | None` 查询；该元数据**不进** LLM schema（与 `risk_level`/`connector` 一致，经 `_OUT_OF_BAND` 同类处理或独立元数据表，不出现在 `_build_schema`）。
- 全局默认 `DEFAULT_TOOL_TIMEOUT`（秒，默认 `30.0`）：模块级常量，可 monkeypatch 注入；亦可经全局配置项覆盖（承载位置见下）。
- 有效超时 = `get_timeout(name)`（非 None 时）否则全局默认。

**为何**：tools.md 明确「可在 `@tool` 声明，默认 30s」；per-tool 覆盖让慢工具（大文件 IO、长查询）可放宽、危险工具可收紧。元数据表范式与 `_risk_levels`/`_connectors` 一致，复用既有「平行元数据、不进 schema」做法，零新机制。模块级常量可 monkeypatch 满足「禁止全局可变状态、可注入」。
**Alternatives**：①只全局不 per-tool——被否，tools.md 要求 per-tool 可声明，且不同工具时延差异大；②把 timeout 塞进 LLM schema 让模型设——被否，超时是平台安全策略，不该由模型控制，且与既有 out-of-band 元数据原则冲突。
**全局默认承载位置（Open Question）**：模块级常量（`agent_loop.DEFAULT_TOOL_TIMEOUT` 或 `tool_registry`）最简且天然可 monkeypatch；若需运维 yaml 配置，可经 `config.Settings` 字段或 settings.yaml 段承载——实现时定，spec 只约束「默认 30s、可注入/可覆盖」。

### D4：超时不影响未超时路径与不协作工具的正确收尾
- 未在时限内的工具：行为与现状完全一致（不构造受限 token 也不改变返回）——即超时仅在「超过时限」分支生效。
- 不声明接受 `cancel_token` 的工具：仍受 await 层竞速保护（主循环停止等待）。`asyncio.wait_for` 超时会向工具协程抛 `CancelledError` 并等其取消，故**纯异步协程本身会被 `wait_for` 取消 unwind**（在下一个 await 点退栈），并非「后台继续跑」。本 change**不强杀工具 spawn 的外部 OS 资源**（docker 容器、subprocess 等不被 asyncio 取消杀掉）——对 `run_code` 这类需真正终止容器内执行的场景，由 SB7 的 `docker kill`（SIGTERM→SIGKILL）负责容器侧硬终止。spec 用 scenario 锁定「主循环停止等待并返回 tool_timeout」，不约束工具 spawn 的外部 OS 进程/容器是否立即终止（划归 SB7/工具自身协作）。

**为何**：诚实划清「await 层不阻塞 + 纯异步协程被 `wait_for` 取消 unwind」（本 change 保证）与「外部 OS 进程/容器真正终止」（协作式工具自己退出 / SB7 容器侧 `docker kill` 硬杀）的边界，避免承诺无法安全兑现的「强杀任意外部资源」。

## Risks / Trade-offs

- [不查 token 且无法被竞速安全中止的工具，超时后协程仍在后台运行占资源] → 本 change 保证 await 层不阻塞主循环并归类返回；后台真正终止由工具协作（查 token）或 SB7（容器 `docker kill`）负责；design D4 + spec scenario 明确此边界，不静默假装已强杀。
- [全局默认 30s 对某些慢工具过短导致误超时] → per-tool `@tool(timeout=...)` 覆盖 + 全局默认可注入/可配；spec scenario 覆盖 per-tool 覆盖全局。
- [超时被误归为 `tool_crash` 或 `unknown`] → D2 明确归 `tool_timeout` 并读 AR5 既有标志位；spec scenario 断言超时分类码为 `tool_timeout`、错误文本指明超时。
- [异步超时测试不稳定 / 真实长 sleep 拖慢测试] → 测试注入极短超时（如 `0.01s`）配可控慢工具 stub（`asyncio.Event` / 受控 `sleep`），不依赖墙钟长等待；CLAUDE.md「异步超时用可控方式测」。
- [接入使 `tool_timeout` 可达后，AR5「预留码不可达」的旧表述过时] → 由本 change 的 ADDED 需求超越（如 AR19 对 `cancelled` 的处理范式）；本 change 不 MODIFY AR5 spec，避免归档顺序敏感。

## Open Questions

- 全局默认超时承载：模块级常量（最简、天然可 monkeypatch）vs `config.Settings`/settings.yaml（运维可配）？实现时定，spec 只约束「默认 30s、可注入/可覆盖」。
- `tool_timeout` 归类接入点：扩展 `error_classifier._categorize` 识别 `TimeoutError`（D2-a）vs 工具层直接读表映射（D2-b，与 `mcp_client` 一致）？两者可观察行为等价，实现时择一。
- 是否需要把生效的工具超时（全局默认 / per-tool）写入 trace 便于运维核对慢工具？（本 change 暂不要求，留待观测类 change）
