## Context

AR2（`src/fleetent/budget.py`）已落地**单次运行**三维预算：

- `BudgetConfig(frozen)`：`max_turns: int / max_tokens: int / max_cost_usd: float`，各以 `NO_LIMIT=-1` 表无上限；`exhausted_dimension(usage)` 按 `turns→tokens→cost_usd` 顺序返回首个达上限的维度名或 None。
- `BudgetUsage`（可变）：`turns/tokens/cost_usd`；`add(prompt_tokens, completion_tokens, model)` 是唯一累计入口（`turns += 1`、`tokens += prompt+completion`、`cost_usd += token/1000 × 单价`，单价查 `MODEL_PRICING`，表外用 `DEFAULT_PRICING`）。
- `BudgetChecker(config, usage)` 实现 AR1 `TerminationChecker`，任一维度达上限返 `StopReason.budget_exceeded` 并记 `triggered_dimension`。

AR2 的预算**只覆盖一次 `run()`/`run_stream()`**：`BudgetUsage` 由每次运行 new 一个 per-run 实例，运行结束即丢弃。`docs/capabilities/agent-runtime.md`「运行治理」要求把预算扩展到**五个层级**（单次任务 / 单 session / 单用户 / 单 agent / 全局），其中 session / user / agent / global 四层天然**跨运行累计**，必须落盘。

约束（CLAUDE.md）：无 AI 框架；无 ORM（用标准库 `sqlite3`，不用 aiosqlite）；禁止全局可变状态（DB 路径常量可 monkeypatch）；新模块 import → 常量 → 数据类 → 函数；mypy strict 全注解；行长 100；TDD Hard Gate；测试 SQLite 隔离到 tmp_path、LLM 调用 mock；不吞异常（DB/解析错误要 log 或 re-raise）。

**既有契约归属**：`budget.py`（AR2）的计量契约不在本 change 范围内修改，仅作依赖引用。本 change 全部能力为新增，以新 capability `agent-cost-budget` 下 ADDED 表达。

## Goals / Non-Goals

**Goals:**
- 定义五层 `BudgetScope` 枚举：`task` / `session` / `user` / `agent` / `global`，与 roadmap 五层一一对应。
- 定义 `LayeredBudgetConfig`：每层一份复用 AR2 `BudgetConfig`，未配置层全 `NO_LIMIT`。
- `BudgetStore`（`sqlite3`）跨运行累计 session / user / agent / global 四层用量，累计口径**复用** `BudgetUsage.add` 的单价换算。
- `LayeredBudgetChecker` 聚合五层检查，任一层超限返回 `StopReason.budget_exceeded`，记录**触发层级 + 触发维度**。
- 系统内部操作（压缩、Grace Call）豁免：沿用 AR2「只有主循环推进任务的 LLM 调用走 add」契约。

**Non-Goals:**
- 不重造计量：单价表、`add` 累计口径、`exhausted_dimension` 判定全部复用 `budget.py`。
- 不重写 Grace Call：复用 AR2 既有 `budget_exceeded` → Grace Call 收尾路径与其 token 隔离比例（5% / 保底 512，wave2 已决）。
- 不实现滚动窗口（rolling window，按「最近 N 小时/天」滑动统计）——本 change 用日历翻滚窗口（tumbling），重置策略见 D7。
- 不实现管理 API / CLI 查询当前用量（运维核对）——列入 Open Questions。
- 不引入新依赖。

## Decisions

### D1：五层用 `BudgetScope` 枚举，层级名严格对齐 roadmap
新增 `BudgetScope(StrEnum)`：`TASK="task"` / `SESSION="session"` / `USER="user"` / `AGENT="agent"` / `GLOBAL="global"`，对应 roadmap「单次任务 / 单 session / 单用户 / 单 agent / 全局」。检查顺序固定为 `task → session → user → agent → global`（由窄到宽），多层同超时报最窄层（确定性，便于 trace 归因与运维定位「最先该卡哪一层」）。

**为何**：StrEnum 与 AR1 `StopReason`、`NetworkPolicy` 等既有枚举风格一致，str 值可直接写 JSONL trace。层级顺序固定保证多层同超时的报告确定性。
**Alternatives**：①用裸字符串常量——被否，无类型约束、易拼写漂移；②层级顺序可配置——被否，过度设计，固定「由窄到宽」语义清晰且足够。

### D2：`LayeredBudgetConfig` 每层一份 AR2 `BudgetConfig`，未配置层全 `NO_LIMIT`
`LayeredBudgetConfig`（dataclass）：`per_scope: dict[BudgetScope, BudgetConfig]`。未在 dict 中的层等价于 `BudgetConfig(NO_LIMIT, NO_LIMIT, NO_LIMIT)`（不拦截）。提供 `from_settings(settings) -> LayeredBudgetConfig` 从 `Settings` 的 `agent_budget_{scope}_{dim}` 字段构造（缺省 `NO_LIMIT`）。

**为何**：直接复用 AR2 `BudgetConfig` 的三维 + `NO_LIMIT` 语义，零计量重造；默认全 `NO_LIMIT` 使既有部署不被新层级意外拦截（与 AR2 token/cost 默认 `NO_LIMIT` 的向后兼容取向一致）。
**Alternatives**：①给每层定义新的独立 config 类——被否，与 AR2 维度集重复，违反「不重造计量」；②把五层上限塞进单个扁平 dataclass（15 个字段）——被否，`dict[BudgetScope, BudgetConfig]` 更内聚、可按层迭代检查。

### D3：跨运行累计用 `BudgetStore`（`sqlite3`），累计口径复用 `BudgetUsage`，主键含 period
新增 `BudgetStore`：模块级 `DB_PATH: Path`（默认 `data/users.db`，可 monkeypatch），建表 `budget_usage(scope TEXT, key TEXT, period TEXT, turns INTEGER, tokens INTEGER, cost_usd REAL, PRIMARY KEY(scope, key, period))`。**主键含 `period` 是预算重置的承载机制**（见 D7）。
- `key` 语义：`session`→session_id、`user`→user_id、`agent`→agent_id、`global`→固定哨兵（如 `"__global__"`）。`task` 层**不落盘**（单次运行即任务，由 AR2 per-run `BudgetChecker` 承载，见 D4）。
- `period` 语义：由**可注入时钟（UTC `now`）**按该层窗口算出（见 D7），落入主键，使跨周期累计天然分行。
- `add(scope, key, prompt_tokens, completion_tokens, model, *, now)`：先用 AR2 `BudgetUsage().add(...)` 算出本次增量的 `turns/tokens/cost_usd`（单一换算来源），再由 `now` + 该层窗口算出 `period`，`INSERT ... ON CONFLICT(scope, key, period) DO UPDATE` 原子累加到对应周期行。
- `get(scope, key, *, now) -> BudgetUsage`：按 `now` 算出当前 `period`，读出该周期累计行，包成 `BudgetUsage` 返回（与 AR2 `exhausted_dimension(usage)` 接口对齐）；无行则返回全 0（天然从 0 起）。

**为何**：session/user/agent/global 需跨运行累计，必须落盘；用 `sqlite3` 直接写 SQL（CLAUDE.md 禁 ORM）。把单次增量换算委托给 `BudgetUsage().add`，单价表/口径只此一处（`budget.py`），`BudgetStore` 只负责持久化累加——职责单一、不重造计量。`ON CONFLICT(scope, key, period) DO UPDATE` 原子累加避免读-改-写竞态。`period` 入主键让重置成为「涌现」而非显式操作（见 D7）。
**Alternatives**：①每层都落盘（含 task）——被否，task = 单次运行，AR2 per-run `BudgetUsage` 已覆盖，落盘是浪费且引入清理负担；②在 `BudgetStore` 内重算单价——被否，违反「不重造计量」，单价表会出现两份；③主键不含 period、靠定时清零实现重置——被否，见 D7。

### D4：`LayeredBudgetChecker` 只聚合 4 个跨运行层，task 归 AR2
`LayeredBudgetChecker(config: LayeredBudgetConfig, store: BudgetStore, *, session_id, user_id, agent_id, clock)` 实现 `TerminationChecker`：
- `check(state)` 按 `session → user → agent → global` 顺序（**只迭代 4 个跨运行层，不含 task**），对每层取 `store.get(scope, key, now=clock())`，调用**该层 `BudgetConfig.exhausted_dimension(usage)`**（复用 AR2 判定）。
- 任一层返回非 None 维度，即记录 `triggered_scope` / `triggered_dimension` 并返回 `StopReason.budget_exceeded`；全未超返回 None。
- `task` 层完全由 AR2 既有的 per-run `BudgetChecker` 承载——它本就管单次运行的三维即时停（仍独立注册到同一 `TerminationController`）。本 change **不在 `LayeredBudgetChecker` 内重复判定 task，也不新增 `agent_budget_task_*` 配置**。`BudgetScope` 枚举仍保留 `task` 成员以维持概念完整，但检查器迭代集与 `Settings` 字段均不含 task。
- 某层 `key` 缺失（如纯 CLI 运行无 session_id/user_id）时**跳过该层检查**，既不归入空 key、也不混入其他桶（见 D7 末与 OQ 收口）。

**为何**：检查逻辑完全复用 AR2 `exhausted_dimension`（每维度判定不重写），`LayeredBudgetChecker` 只做「逐层取 usage + 聚合首个超限」。task 与 AR2 per-run `BudgetUsage` 语义等价，交由 AR2 `BudgetChecker` 单点负责可**消除双判与配置重复**——避免「同一单次运行被两个检查器各判一次」「task 上限在 `agent_budget_task_*` 与 AR2 `agent_max_*` 两处重复声明」。两者都注册到同一 `TerminationController`，`should_stop` 返回首个非 None：AR2 管 per-run（含 task）即时停，本 change 管 4 个跨运行层。`triggered_scope` + `triggered_dimension` 双字段供 trace 精确归因。
**Alternatives**：①把五层判定塞进 AR2 `BudgetChecker`——被否，会污染 AR2 单运行契约（被 MR2 等其他波次 3 能力依赖），层级聚合应独立；②`LayeredBudgetChecker` 也判 task（含 `agent_budget_task_*` 配置）——被否，与 AR2 per-run 预算完全重复，造成双判与配置两处声明；③`key` 缺失时归入空字符串/哨兵桶——被否，会把无关运行混入同一桶导致误限，跳过更安全。

### D5：累计写入点与豁免——沿用 AR2「主循环推进 add」契约
主循环每轮 LLM 调用结算后（AR2 已有的 `_budget_add(usage, response.usage, model)` 落点旁），对 session/user/agent/global 四层各调一次 `store.add(scope, key, prompt, completion, model)`。压缩调用、Grace Call 自身**不经过此落点**（AR2 已确认压缩 token 不流经主循环 `response.usage`），故天然豁免，无需主动识别排除。

**为何**：豁免语义与 AR2 完全一致（roadmap「系统内部操作可豁免」），复用既有「只有主循环推进任务的调用走 add」边界，不新增豁免开关。
**Alternatives**：在 `BudgetStore.add` 内加 `is_internal` 标志显式排除——被否，AR2 已证明「不接入即豁免」更简单可靠，避免每个调用点判定内部/外部。

### D6：超限收尾复用 AR2 Grace Call 路径
跨运行层任一超限返回 `StopReason.budget_exceeded`，与 AR2 单运行超限**同一终止原因**，因此自动复用 agent_loop 既有的 `budget_exceeded` → Grace Call 收尾（非流式 `_grace_call`、流式内联），含其 token 隔离（5% / 保底 512，wave2 已决）。超限时经 `log_run` 写入可选字段 `budget_scope`（触发层级），沿用波次2 `disabled_skills_trace` 在 `log_run` 加可选字段的范式，以区分是哪一层触发。

**为何**：roadmap 要求「到达上限触发 Grace Call，不硬切断」，AR2 已实现该路径且经 wave2 决策定型；层级超限语义上等价「预算耗尽」，复用同一收尾零重写。`budget_scope` 走 `log_run` 可选字段与波次2 一致，不新建 trace 通道。
**Alternatives**：为层级超限定义新 StopReason（如 `layer_budget_exceeded`）——被否，会让 agent_loop 出现两条几乎相同的 Grace Call 分支，且 `budget_exceeded` 语义已涵盖。

### D7：预算重置用日历翻滚窗口（tumbling）+ 周期入主键的涌现式重置
跨运行层的累计 SHALL 按**日历翻滚窗口**重置，而非单调累加到永久。重置不是一个操作，而是 D3 主键含 `period` 的**涌现结果**：

- **窗口取值集** `BudgetWindow`：`{lifetime, daily, weekly, monthly}`。`period` 由**可注入时钟（UTC `now`）**按该层窗口算出：
  - `lifetime` → 串 `"lifetime"`（与时钟无关，永不变）
  - `daily` → `"YYYY-MM-DD"`
  - `weekly` → ISO 周 `"YYYY-Www"`（周一起，`now.isocalendar()` 取年与周号）
  - `monthly` → `"YYYY-MM"`
- **重置 = 涌现**：跨周期后，`add`/`get` 用新的 `now` 算出的 `period` 变了 → 落到新主键行 → 该行从 0 起累计，旧周期行不再被读到。**不引入任何定时清零操作、不依赖调度器、无读-改-写竞态**——契合 CLAUDE.md「无全局可变状态 / 不依赖调度器」。
- **各层默认窗口**：`session`→`lifetime`（按 session_id 自限，session 本就有界，不做日历重置）；`user`→`weekly`；`agent`→`weekly`；`global`→`monthly`；`task`→不适用（归 AR2，见 D4）。窗口仅在该层配了上限时才起作用（无上限层不读 store）。
- **配置**：每层一个窗口字段经 `Settings` 暴露——`agent_budget_user_window` / `agent_budget_agent_window` / `agent_budget_global_window`（取值 `BudgetWindow` 之一）。`session` 固定 `lifetime` **不可配**（无对应 Settings 字段）。时区 v1.0 **固定 UTC**（可配时区列入 OQ）。
- **旧周期行**：保留（每行极小，可作历史供 admin 查用量）；周期行 prune/归档不在本 change（列入 OQ）。
- **时钟可注入**：`BudgetStore.add/get` 与 `LayeredBudgetChecker` 接受可注入 `clock`（默认 `lambda: datetime.now(UTC)`），用于测试跨周期翻滚的确定性。

**为何**：roadmap 的「配额周期」需要重置，但**滚动窗口**（最近 N 小时滑窗）要为每次查询扫描时间序列、存每条记录、复杂度高，对 on-premises 单库治理是过度设计；**定时清零**需要后台调度器定期 UPDATE/DELETE，与「不依赖调度器」冲突，且清零与并发 add 之间有读-改-写竞态。日历翻滚窗口把「当前周期」编码进主键，重置随时钟自然涌现——无操作、无调度、无竞态，且天然多 worker 安全（都对同一 period 行做 `ON CONFLICT` 原子累加）。
**Alternatives**：①滚动窗口（rolling/sliding）——被否，过度设计，需存逐条时间序列并按窗口聚合，治理场景用不上这种精度；②定时清零（scheduler 周期 UPDATE 归零）——被否，引入调度器依赖且与并发 add 存在读-改-写竞态；③`period` 不入主键、靠应用层判断当前周期——被否，等价回到读-改-写，失去原子性。

### D8：暴露 `headroom()` 生产者 + `BudgetHeadroom` 类型供成本感知路由消费
兄弟 change `cost-aware-routing`（MR2）需要「当前预算最紧层的 cost 剩余比例」来做成本感知路由决策。这套「遍历五层、找最紧层、算剩余比例」的逻辑是本 change 五层迭代的**对偶**——`LayeredBudgetChecker` 找「最紧的超限维度」，`headroom` 找「最紧层的剩余比例」。按信息专家原则，由**拥有分层预算配置（`LayeredBudgetConfig`）+ 累计存储（`BudgetStore`）的本 change（AR18）拥有并暴露**，而非让 agent_loop / MR2 重算（重算会泄漏本 change 的层级结构）。

- 新增**只读值对象 `BudgetHeadroom`**（frozen dataclass）：至少含
  - `cost_remaining_ratio: float`（∈[0,1]，最紧层 `cost_usd` 剩余/上限；该层无上限不参与计算，全层无任何 cost 上限时为 `1.0` 表充裕）
  - `tightest_scope: str | None`（触发最紧的层名，供 trace 归因；全层无 cost 上限时为 None）
- 新增 `headroom(session_id, user_id, agent_id) -> BudgetHeadroom` 生产者：**复用本 change 已有的跨运行层迭代内核**（与 `LayeredBudgetChecker` 同一套「遍历 session/user/agent/global 四层、读 `BudgetStore` 当前周期累计、对照 `LayeredBudgetConfig` 上限」逻辑）。对每个配了 `cost_usd` 上限的层算 `剩余比例 = (上限 - 累计) / 上限`，取最小者作为 `cost_remaining_ratio`、记其层名为 `tightest_scope`；无任何层配 cost 上限时返回 `cost_remaining_ratio=1.0`、`tightest_scope=None`。某层 `key` 缺失时**跳过该层**（沿用 D4「key 缺失跳过该层」决策）。
- **类型定义在本 change（AR18）**：`BudgetHeadroom` 是「五层中最紧层」的概念、天生属分层预算；且依赖方向是 MR2→AR18（路由依赖预算），类型放这里 MR2 才能 import，反之会让 AR18 反向依赖 MR2，破坏依赖方向。
- 这是供 MR2 消费的**只读快照生产**：`headroom()` 不改本 change 既有的检查（`LayeredBudgetChecker`）/ 累计（`BudgetStore.add`）/ Grace Call 任何逻辑，只读取当前周期累计算出剩余比例快照。

**为何**：①**信息专家**——「遍历五层 + 对照上限」的层级结构与配置/存储都在本 change，剩余比例计算与超限检查共用同一迭代内核，由本 change 拥有可避免逻辑复制与结构泄漏；②**依赖方向**——MR2（路由）依赖 AR18（预算），类型与生产者放 AR18 使 MR2 单向 import，符合「路由依赖预算、预算不知路由」。
**Alternatives**：让 agent_loop / MR2 自行遍历层级、读 store、算剩余比例——被否，等于在 MR2 重写本 change 的五层迭代、把本 change 内部的层级结构（默认窗口、key 语义、哨兵）泄漏到路由层，且产生两份「遍历层级」逻辑随 D1/D4 演进而漂移。

## Risks / Trade-offs

- [预算重置语义] → 用日历翻滚窗口（D7），`period` 入主键、重置随时钟涌现，无需运维手动清表；spec 用 scenario 覆盖「跨周期归零」「lifetime 永不重置」「各层默认窗口」。旧周期行 prune 列入 OQ。
- [多 worker 并发写同一 `(scope, key, period)`] → `ON CONFLICT DO UPDATE` 原子累加避免读-改-写丢失；sqlite3 写锁串行化，on-premises 单库部署可接受。高并发分布式计数列入 Open Questions。
- [`store.add` 每轮额外四次 DB 写] → 单次 LLM 调用耗时远大于本地 sqlite 写，开销可忽略；四层写可合并为一条多行 `executemany`（实现细节）。
- [`LayeredBudgetChecker` 与 AR2 `BudgetChecker` 职责切分] → 两者都注册，`should_stop` 返回首个非 None；task 层只由 AR2 per-run `BudgetChecker` 负责，`LayeredBudgetChecker` 只迭代 session/user/agent/global 四层（D4 已定），无双判、无配置重复。
- [`global` 哨兵 key 与真实 id 冲突] → 用不可能作为 id 的固定哨兵（如 `"__global__"`）规避；spec scenario 断言 global 累计独立于任何 user/agent。
- [`key` 缺失（纯 CLI 无 session_id/user_id）] → 该层跳过检查（D4），不归入空 key 桶，避免无关运行混桶误限。

## Open Questions

- 是否需要 admin CLI / `/health` 暴露各层当前累计用量供运维核对与告警？
- 多 worker / 分布式部署下的预算计数一致性（当前依赖单 sqlite 库写锁）——是否需要 Redis 计数器后端（自托管，符合数据主权）？
- 时区可配：v1.0 窗口固定 UTC，是否需要按部署时区计算 `period` 边界（影响 `daily`/`monthly` 的翻滚时刻）？
- 旧周期行 prune/归档：过期 `period` 行（已不被读到）何时清理或归档，是否需要后台任务？
