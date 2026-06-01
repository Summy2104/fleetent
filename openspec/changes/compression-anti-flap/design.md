## Context

AR12（`context_mgr.py`，spec `openspec/specs/context-compression-threshold/spec.md`）已实现双阈值压缩：

- `maybe_compress(messages, config, *, force)`：自动路径在 `estimate_tokens(messages) > max_tokens * Tmax` 时调 `_compress`，否则原样返回；`force=True` 为手动 `/compact`，无条件压缩。
- `compress_for_context_overflow(messages, config)`：LLM 报「上下文过长」时的无条件压缩入口，供调用方 catch-error → compress → retry。
- `_compress` 以 `max_tokens * Tretained` 为目标线分层（头完整保留 / 中段 LLM 摘要 / 尾完整保留），且 spec 明确「目标线让位于工具对完整性」——压缩后实际值 MAY 略高于 `Tretained`。
- `_resolve_config` 强制 `Tretained < Tmax` 间距不变式；配置经 `ContextConfig` dict 注入或 `Settings` env 字段，无全局可变状态。

**调用链与持久化事实**（影响反抖动状态作用域的关键背景）：

- `maybe_compress(messages)` 在 `agent_loop.run()` / `run_stream()` 的 while 主循环里**每 turn 调用一次**（每轮 LLM tool-use 前先尝试自动压缩）。
- 一次 `run()` = 处理**一条用户消息**（内部可能多 turn）；一个 **session** = 跨**多次 `run()`**（多条用户消息）的会话生命周期。
- `session_mgr.load/save` 持久化的是**裸 JSON 消息数组**——没有承载「session 级附加状态」的位置；若往里塞反抖动状态会破坏其裸数组契约。
- 典型抖动是**跨 run 的慢性抖动**：context 预算偏小 + 多轮对话，每条用户消息触发一次压缩，连续若干条用户消息都低节省。若反抖动状态只活在单次 `run()` 的内存里，则跨 run 永远数不到「连续 3 次」，熔断空转、形同虚设。`docs/capabilities/agent-runtime.md` 的补救提示「扩大 context 上限或拆分任务」也正指向这种慢性跨 run 场景。

AR12 的间距不变式只解决「压缩有效时」的即时再触发。它无法处理**压缩低效**的抖动：中段可压缩内容少时，一次压缩省不下多少 token，压缩后仍贴近 `Tmax`，于是反复「压缩→几乎没省→再压缩」，烧 LLM 成本并反复击穿 prompt 缓存前缀，却救不回上下文。`docs/capabilities/agent-runtime.md`「压缩反抖动」给出治理规则：**连续 3 次压缩节省率均低于 10% → 关闭自动压缩并告警**。

约束（CLAUDE.md）：禁止全局可变状态（窗口/阈值为可注入常量；反抖动**统计状态**由会话持有、按次传入，不落模块级可变全局）；禁止 AI 框架；禁止 ORM；mypy strict 全注解；行长 100；TDD Hard Gate；测试 mock LLM、状态与路径隔离；不吞异常（告警须 log，不静默）。

## Goals / Non-Goals

**Goals:**
- 定义反抖动**状态**（最近 N 次自动压缩节省率、自上次压缩以来的新增 turn 计数、自动压缩是否已被熔断关闭），作用域为 **session 生命周期级**，**按 session_id 持久化于 `users.db`**（复用 `session-metadata-index` 已有的 per-session sqlite 家），由 `agent_loop` 在 run 边界 load/save、按次传入 `maybe_compress`，turns 计数随对话**跨 run 累计**，无全局可变状态。
- 定义节省率：`savings = (before_tokens - after_tokens) / before_tokens`（`before_tokens > 0`，否则记 0）。
- **低节省熔断**：连续 `flap_window`（默认 3）次自动压缩节省率均 `< min_savings_ratio`（默认 0.10）→ 关闭该会话自动压缩 + 发结构化告警（提示扩大 context 上限或拆分任务）。
- **最小间隔/滞后窗口**：两次自动压缩之间须间隔 ≥ `min_interval_turns`（默认 1）个新增 turn，窗口内自动压缩被跳过。
- 手动 `/compact` 与 overflow 入口**不受**熔断与间隔门控（正确性兜底）。
- 全部阈值/窗口可注入（`ContextConfig` dict + `Settings` env），与 AR12 一致。

**Non-Goals:**
- 不改 AR12 的 `Tmax`/`Tretained` 判定、`_compress` 分层、间距不变式。
- 不实现「自动扩大 context 上限」或「自动拆分任务」——熔断只关闭自动压缩并告警，由人/上层决策。
- 不实现循环检测 / 工具调用守卫（AR 其它功能点）、不实现压缩可追溯日志的完整 trace schema（AR16，本能力只发反抖动相关的最小告警事件）。
- 不引入新依赖。

## Decisions

### D1：反抖动状态为 session 级，按 session_id 持久化于 `users.db`，按次传入 + agent_loop 在 run 边界 load/save
新增 `AntiFlapState`（dataclass）：
- `recent_savings: tuple[float, ...]`（最近 ≤ `flap_window` 次自动压缩的节省率，定长滑窗）。
- `turns_since_last_compress: int`（自上次自动压缩以来新增的 turn 数，用于最小间隔窗口）。
- `auto_disabled: bool`（自动压缩是否已被熔断关闭）。

**作用域与持久化**：`AntiFlapState` 的作用域为 **session 生命周期级**，**按 session_id 持久化于 `users.db`**——**复用 `session-metadata-index`（已实现）在 `users.db` 维护的 per-session sqlite 家**：在其 `sessions` 表追加反抖动列，或建一张以 `session_id` 为键的姊妹表（实现期二选一）。**不塞进 `session_mgr` 的裸消息数组文件**，从而保留其裸数组契约不破坏，也不触碰 metadata-index / ttl-cleanup / disk-management 这几个已实现 change 的既有行为。持久化用标准库 `sqlite3` 直写 SQL（与 `sub_agent_runs` / budget store 同款范式：复用 `_conn()`、`CREATE TABLE/INDEX IF NOT EXISTS`、`DB_PATH` 从 `user_store` re-export 可 monkeypatch），无全局可变状态、无 ORM、不新建 db 文件。

**按次收发 + run 边界 load/save**：`maybe_compress` 新增可选入参 `state: AntiFlapState | None`：为 None 时退化为 AR12 现状（无反抖动门控，行为不变，保兼容）；传入时执行门控并**返回**更新后的状态（不就地改写传入对象，纯函数式更新）。状态的生命周期由 **`agent_loop` 在 run 边界管理**：开 `run()` 时按 `session_id` 从 `users.db` 读出 `AntiFlapState`，逐 turn 把它传入 `maybe_compress` 并接住返回值，run 结束（或每次发生压缩）后写回 `users.db`。因此 `turns_since_last_compress` 与 `recent_savings` 随对话**跨多次 `run()`（多条用户消息）累计**——这正是命中 doc 主场景「跨 run 慢性抖动」、让「连续 3 次低节省」可被数到的关键。

**清理**：随 session 删除/过期清掉该行（挂到 session cleanup 路径），或留极小 stale 行——二选一在实现期定，本 spec 不锁（见 Open Questions）。

**为何**：CLAUDE.md 禁止全局可变状态；反抖动需要跨多次 `maybe_compress`、**跨多次 `run()`** 记忆历史，否则跨 run 慢性抖动永远数不到「连续 3 次」、熔断空转。`maybe_compress` 保持纯函数式（按次收发、不就地改写），把「记忆从哪来、存到哪去」的副作用收敛到 `agent_loop` 的 run 边界与 `users.db` 旁路，既满足无全局可变状态，又让 session 级持久化与 `session-metadata-index` 共用一套 per-session sqlite 家，测试可直接构造 `AntiFlapState` 注入、或 monkeypatch `DB_PATH` 到 tmp_path 隔离。
**Alternatives**：①把裸消息数组改成带附加状态的对象——被否，破坏 `session_mgr` 裸数组契约、牵动 metadata-index / ttl / disk-management 等已实现 change；②模块级 `dict[session_id, history]` 缓存——被否，正是 CLAUDE.md 明令禁止的全局可变状态，且测试隔离困难；③per-run 内存态（状态只活在单次 `run()`）——被否，漏掉 doc 主场景「跨 run 慢性抖动」，跨 run 数不到连续 3 次、熔断形同虚设；④把状态塞进 messages——被否，污染对话内容且 `estimate_tokens` 会误算。

### D2：节省率统计只计自动压缩，定长滑窗 + 连续判定
- 节省率 `savings = (before - after) / before`（`before <= 0` 记 0，避免除零）。
- 每次**自动**压缩（含「越线但低节省」的压缩）后，把 `savings` 追加进 `recent_savings`，仅保留最近 `flap_window` 个。
- 当 `len(recent_savings) == flap_window` 且**全部** `< min_savings_ratio` → 置 `auto_disabled = True` 并告警。
- 手动/overflow 压缩不计入 `recent_savings`（不代表自动抖动，且无条件压缩）。

**为何**：doc 要求的是「连续 N 次低节省」，定长滑窗 + 全部低于阈值即「连续」；一旦某次节省达标，滑窗里混入高值，`all(... < ratio)` 自然为假，连续性被打断，符合「连续」语义。只计自动压缩避免 `/compact`（用户主动、可能本就没多少可省）误触熔断。
**Alternatives**：①累计计数器 + 命中即清零——可行但需额外字段；定长 `tuple` 滑窗 + `all()` 更直观且天然定长不增长。②对节省率做指数衰减平均——过度设计，doc 只要「连续 3 次」的简单规则。

### D3：最小间隔 / 滞后窗口以「新增 turn 数」计，turns 计数跨 run 累计
- `maybe_compress` 自动路径在判定 `Tmax` 越线后，先检查 `turns_since_last_compress >= min_interval_turns`；不满足则**跳过本次自动压缩**（原样返回 messages），不调用 LLM。
- `turns_since_last_compress` 随对话推进**跨 run 累计**：`maybe_compress` 每被调用（每 turn）一次即推进计数，且因 `AntiFlapState` 由 `agent_loop` 在 run 边界从 `users.db` load/save（见 D1），计数不在单次 `run()` 结束时清零，而是跨多次 `run()`（多条用户消息）持续累加，直到真正执行一次自动压缩才归零。
- 一旦真正执行自动压缩，`turns_since_last_compress` 归零。

**为何**：AR12 间距不变式针对「压缩有效」场景；当压缩在 `Tmax` 擦边（low watermark 余量不足）时，同一批消息可能在相邻两次检查里都越线，滞后窗口确保不在紧邻的 turn 上连发压缩，给新增内容累计的时间，与 prompt 缓存的稳定前缀目标一致。turns 跨 run 累计与 session 级持久化（D1）一致：抖动是跨用户消息的慢性现象，计数必须跨 run 才能反映真实的压缩频率。
**Trade-off**：窗口内若 LLM 真报 context-overflow，靠 `compress_for_context_overflow`（不受窗口门控）兜底，正确性不受损；窗口只约束「自动预防性压缩」的频率。
**Alternatives**：以「墙钟最小间隔秒」计——被否，agent turn 节奏差异大，墙钟易在慢会话上失效或在快会话上过严；以 turn 计与压缩语义直接对应。

### D4：手动 `/compact` 与 overflow 入口豁免反抖动门控
- `maybe_compress(force=True)`：跳过熔断与间隔判定，无条件压缩（保留 AR12 手动语义）；其节省率不计入 `recent_savings`。
- `compress_for_context_overflow`：完全不经反抖动门控，无条件压缩（LLM 已报错，正确性优先于反抖动）。

**为何**：反抖动是对「自动预防性压缩」的频率治理；手动是用户显式意图，overflow 是正确性硬需求，二者都不应被熔断或窗口阻断，否则会在熔断后让会话无法恢复或在 overflow 时拒绝压缩导致请求必失败。
**Alternatives**：熔断后连手动也禁止——被否，熔断的本意是停掉「无效的自动循环」，而非剥夺用户/兜底路径的压缩能力。

### D5：熔断告警为结构化日志 + 状态标志，不抛异常
熔断时 `logger.warning("compression_auto_flap_disabled", recent_savings=..., min_savings_ratio=..., flap_window=...)` 并置 `auto_disabled=True`。上层可读 `state.auto_disabled` 决定是否向用户提示「扩大 context 上限或拆分任务」。

**为何**：CLAUDE.md 不吞异常但反抖动熔断是**正常治理路径**而非错误，抛异常会打断主循环；用日志 + 可读状态标志暴露，让 agent_loop / 上层按需提示，符合「不静默」与「不崩主循环」双重要求。
**Alternatives**：抛自定义异常让上层 catch——被否，把治理决策做成控制流异常，污染错误分类（AR 错误处理矩阵）。

## Risks / Trade-offs

- [熔断后会话永久无法自动压缩] → `auto_disabled` 是会话级状态，会话结束即释放；且手动/overflow 仍可压缩；告警提示用户扩大上限或拆分任务，由人解除。spec 用 scenario 覆盖「熔断后手动仍可压缩」。
- [滞后窗口内 token 持续涨、自动压缩被跳过导致溢出] → overflow 入口（`compress_for_context_overflow`，不受窗口约束）兜底；窗口只延后预防性压缩，不阻断正确性路径。
- [节省率阈值/窗口设得过松或过紧] → 全部可注入；默认值取自 doc（连续 3 次 < 10%）与最小间隔 1 turn，保守且与现状行为接近（`state=None` 时完全不变）。
- [`state=None` 与传入 state 行为分叉造成困惑] → 明确：None = AR12 现状（向后兼容、零行为变更）；传入 state 才启用反抖动。spec scenario 覆盖「不传状态时行为与 AR12 一致」。
- [熔断后 context 继续涨、只能等真的 overflow 报错兜底] → 熔断（`auto_disabled=True`）后自动压缩停止，context 仍会随对话增长，此时不再有预防性压缩，只能等 LLM 真的报「上下文过长」、由 `compress_for_context_overflow` reactive 兜底。这意味着**熔断后每次压缩都要先吃一个 failed LLM round-trip**（先报错、再压缩、再重试）。这是**有意取舍**：熔断的本意就是停掉「无效的自动循环」、退回 reactive，用一次性的失败重试成本换取不再反复烧 LLM 摘要调用与击穿 prompt 缓存。明确写出以免误以为熔断后高枕无忧——熔断不是「解决了抖动」，而是「把无效的主动压缩换成了按需的被动压缩」。
- [`min_interval_turns=1` 默认近乎 no-op] → 因 `maybe_compress` 本就**每 turn 调用一次**，`min_interval_turns=1` 意味着「上次压缩后至少新增 1 个 turn」几乎总是满足，间隔窗口默认基本不发力；默认下真正发挥作用的反抖动是 **savings 熔断**。保持默认 `1`（保守、贴近现状、零意外行为）；若部署方需要更强滞后（同批消息上更克制地连发压缩），可调 `min_interval_turns >= 2` 让窗口真正介入。

## Open Questions

- 清理 stale 行的策略：随 session 删除/过期挂到 session cleanup 路径清掉该行，还是留极小 stale 行不主动清理？二选一在实现期定（spec 不锁），不影响反抖动语义正确性。
- 熔断告警是否同时写入 AR16 压缩追溯日志（trace），还是仅发独立 warning 事件？AR16 尚未实现，本能力先发最小 warning，trace 集成留待 AR16 落地后对齐。
- `min_savings_ratio` 是否应区分「节省率」与「回落到 `Tretained` 的余量达成率」两种口径？本能力以节省率（before/after 差）为准，余量达成留作后续增强。
