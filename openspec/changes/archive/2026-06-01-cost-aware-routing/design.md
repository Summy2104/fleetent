## Context

`model_router.py`（MR1，已实现）是 agent_loop 与 LLM provider 之间唯一的中间层，路由**静态**：

- `_load_routes()` 合并内置 `DEFAULT_ROUTES` 与 `config/routes.yaml`，得到 `dict[str, RouteConfig]`。
- `RouteConfig(frozen)`：`base_url / model / api_key_env / max_tokens / fallbacks: tuple[str,...] / params`。`fallbacks` 是 route 名序列，顺序即优先级。
- `RouteOverride(frozen)`：按字段合并到 route 上的请求级覆盖（`_apply_override`）；设 `model` 而不显式给 `fallbacks` 会清空 fallback 链（D3 语义）。
- `get_(async_)client_and_config(task_type, override)`：查 `routes.get(task_type, routes["default"])`，应用 override，按 `api_key_env` 取 key 后构造 `OpenAI/AsyncOpenAI` client。client 无状态、每次新建。

整条路由只看 `task_type` 与显式 `override`，**不看预算**。`docs/capabilities/model-router.md`「规划中（v1.0）」点名「成本感知路由：当月成本接近预算上限时自动降级到 cheap task_type」。

`cost-budget-control`（AR18，本波次 3 已 propose）在 AR2 之上引入五层累计预算（task/session/user/agent/global），每层有上限并跨运行落盘——「当前还剩多少预算」由此成为可读取的运行时状态。AR18 进一步**对外暴露 `headroom(session_id, user_id, agent_id) -> BudgetHeadroom` 生产者**：复用其五层迭代算「最紧层剩余比例」（是 `LayeredBudgetChecker` 找「最紧超限维度」的对偶），并拥有 `BudgetHeadroom` 类型。本 change 从 AR18 import 该类型、消费其标量产出。

约束（CLAUDE.md）：无 AI 框架（直接用既有路由产物，不引抽象层）；无 ORM（本 change 不落盘，不读 DB，仅消费 AR18 暴露的剩余）；禁止全局可变状态（阈值/开关常量可 monkeypatch，policy 按次注入）；新模块 import → 常量 → 数据类 → 函数；mypy strict 全注解；行长 100；TDD Hard Gate；测试 mock client 构造、yaml 路径隔离到 tmp_path、不发真实 LLM 调用；不吞异常（解析/查表错误要 log 或 re-raise）。

**既有契约归属**：`model_router` 的路由/fallback 语义不在本 change 范围内修改，仅作依赖引用；`BudgetHeadroom` 类型与 `headroom()` 生产者归 AR18，本 change 仅消费。本 change 全部能力为新增，以新 capability `cost-aware-routing` 下 ADDED 表达。

## Goals / Non-Goals

**Goals:**
- 消费 AR18 暴露的 `BudgetHeadroom`（只读剩余快照）：表达「最紧层」当前 `cost_usd` 剩余比例与是否进入降级阈值。`BudgetHeadroom` 类型与 `headroom()` 生产者归 AR18，本 change import 类型并消费标量。
- 定义 `CostAwareRoutingPolicy`：把预算紧张级别映射到成本倾向动作（两档：`normal` / `degrade`），degrade 改路由到运维显式配置的 target task_type。
- 在 `model_router` 取得 task_type route 之后、构造 client 之前接入决策（可选 `BudgetHeadroom` 入参），无信号时**逐字节等价现状**。
- 降级阈值/开关/`degrade_target` 从 `Settings` 加载，缺省关闭（向后兼容）。

**Non-Goals:**
- 不重造预算计量：累计与上限、五层聚合、`headroom()` 生产全部属 AR18；本 change 只**消费**其暴露的标量剩余、不重算层级。
- 不在本 change 比价择模型：degrade 走显式配置的 target task_type，不引入单价排序，不依赖 `budget.py` 单价表。
- 不改 `model_router` 的 task_type 查表、fallback 链、override 合并语义（仅旁路追加一层）。
- 不设「重排 fallback 链优先低价」中间档：fallback 链只在主模型失败时用，重排它常态不省钱（真正杠杆是 degrade 换主模型），且按价重排把运维的可靠性优先序改成价格优先序（语义偏移），v1.0 不做（见 D5）。
- 不实现 provider 健康探针缓存（model-router 另一规划项，独立 change）。
- 不引入新依赖。

## Decisions

### D1：`BudgetHeadroom` 与 `headroom()` 归 AR18，本 change 消费标量
`BudgetHeadroom`（frozen dataclass）：`cost_remaining_ratio: float`（最紧层 `cost_usd` 剩余 / 上限，∈ [0,1]；无上限层不参与，全无上限时为 1.0=充裕）+ `tightest_scope: str | None`（触发最紧的层名，供 trace）。**该类型与生产它的 `headroom(session_id, user_id, agent_id) -> BudgetHeadroom` 函数均归 `cost-budget-control`(AR18) 拥有**：AR18 复用自己的五层迭代算「最紧层剩余比例」（这是 `LayeredBudgetChecker` 找「最紧超限维度」的对偶——同一遍迭代，一个找超限维度、一个算剩余比例）。本 change 从 AR18 **import `BudgetHeadroom` 类型并消费其标量产出**，不在 `cost_aware_routing.py` 定义该类型、不在 agent_loop 自算 headroom。agent_loop 瘦编排：`cost_budget.headroom(...)` 拿标量 → 传 `model_router`。

**为何**：让 agent_loop 从 `LayeredBudgetConfig` + `BudgetStore.get` 自算 headroom，会在 agent_loop 里重写 AR18 的层级迭代、泄漏 AR18 内部（五层结构 / sqlite 表 / 哨兵 key）。把生产者收进 AR18（它本就拥有这些事实），路由层只消费一个标量即可决策。依赖方向 cost-aware-routing → cost-budget-control（路由依赖预算，自然方向）；AR18 改累计实现不影响本 change，本 change 也不写 AR18 的库。frozen 保证决策期间信号不被并发修改。
**Alternatives**：①agent_loop 从 `LayeredBudgetConfig` + `BudgetStore.get` 自算 headroom——被否（评审定稿），重写 AR18 的层级迭代、泄漏 AR18 内部；②`model_router` 直接 import AR18 的 `BudgetStore` 自行读库——被否，把路由层耦死到 AR18 的存储实现，破坏 `model_router`「无状态、不碰 DB」的纯函数性质；③传整个 AR18 `LayeredBudgetConfig`+用量——被否，路由层不该理解层级语义，标量剩余比例足够。

### D2：紧张级别→动作用 `CostAwareRoutingPolicy`，两档、阈值可配置、缺省不干预
新增 `CostAwareRoutingPolicy`（dataclass）：一个阈值 `degrade_below: float`（剩余比例低于此 → `degrade`），`degrade_target: str | None`（降级目标 task_type，**默认 None**）。`decide(headroom) -> CostAction`（两档：`normal`/`degrade`）。`from_settings(settings)` 构造；阈值缺省值使整链**不干预**（开关关 / headroom=None 时直接 `normal`）。

**`degrade_target` 默认 None 的语义**：避免「开关一开复杂任务悄悄降到 haiku」的质量悬崖。成本感知启用但**未显式配 target 时 `degrade` 档不可用、`decide` 退回 `normal`**（不擅自降级）；只有运维显式指定 target 时 degrade 才生效。

**为何**：把「紧张程度」离散成两档动作（不干预 / 降级换主模型），决策可预测、可测；阈值配置化满足不同部署的成本敏感度，缺省关闭保证既有部署零行为变化（与 AR18 默认 `NO_LIMIT`、sandbox 默认安全值的向后兼容取向一致）。不给默认便宜 route，杜绝静默质量悬崖。
**Alternatives**：①连续函数动态选模型（按剩余比例线性插值价格档）——被否，过度设计、难测、不可解释；②阈值硬编码——被否，违反 model-router「config 驱动、不硬编码」原则；③`degrade_target` 给默认便宜 route（如 `"memory_extraction"`）——被否，开关一开就把复杂任务悄悄降级，质量悬崖；默认 None + 未配则 degrade 不启用更安全。

### D3：动作落到 `model_router` 既有产物——降级改 route，不另造类型
- `normal`：返回原 route 不变（旁路）。
- `degrade`：把当前 task_type 的解析改为 `degrade_target` task_type 的 route（等价 model-router 文档的「降级到 cheap task_type」），经既有 `routes.get` 路径取得，复用既有 fallback/override 合并。`degrade_target` 为 None 时不进入此档（见 D2）。

**为何**：成本感知的输出必须仍是 `model_router` 能直接消费的 `RouteConfig`（D1 解耦的对偶——本 change 不污染 model_router 的类型）。「降级到 cheap task_type」直接命中文档既定语义。
**Alternatives**：①新增 `CostAwareRoute` 结果类型——被否，会让 model_router 出现两种路由产物、所有下游都要分支；②`degrade` 时直接改 `RouteConfig.model` 为某个写死的便宜模型名——被否，绕过 task_type 路由表，破坏「provider 定义全在 config」原则，应走 `degrade_target` task_type 经既有查表。

### D4：决策接入点——route 解析后、client 构造前，按次可选
在 `get_(async_)client_and_config` 内 `_apply_override` 之后、`OpenAI/AsyncOpenAI(...)` 构造之前，新增可选 `headroom: BudgetHeadroom | None = None`（及可选注入的 `policy`）：`headroom is None` → 跳过（现状路径，逐字节等价）；非 None → `policy.decide(headroom)` 得动作，按 D3 调整 route 后再构造 client。`degrade` 改 task_type 解析时重走 `routes.get(target, routes["default"])` 并复用既有 override 合并次序（override 仍后于降级生效，请求级覆盖优先级最高）。

**为何**：成本感知只影响「选哪个 route/model」，不影响 client 构造方式与 api_key 解析，放在 route 定型后最贴切；可选入参 + None 旁路保证零回归，既有调用方不传 headroom 即与现状完全一致。client 仍每次新建（沿用 MR1「client 无状态、廉价」决策）。
**Alternatives**：①在 agent_loop 侧先决策好再传 `RouteOverride` 给 model_router——可行但把「阈值→动作 / degrade 改 task_type 解析」逻辑漏到调用方且每个调用点重复；集中在 `cost_aware_routing` + 一个接入点更内聚（agent_loop 只负责调 AR18 `headroom()` 取标量、再透传）。②加独立函数 `get_cost_aware_client(...)`——被否，会与既有入口产生两条几乎相同的路径，可选入参旁路更简洁。

### D5：不设「重排 fallback 优先低价」中间档，两档足矣
**v1.0 只有 `normal` / `degrade` 两档，不引入「重排 fallback 链优先低价 provider」的中间档**，相应不读 `budget.py` 单价表。

**为何**：fallback 链只在主模型失败时才用，重排它在常态（主模型正常工作）下**不省钱**——真正的成本杠杆是 degrade 换主模型；按价重排还会把运维在 routes.yaml 里编排的**可靠性优先序**改成**价格优先序**（语义偏移，运维把某 provider 排在前面通常是为可靠性而非价格）；多一个阈值 + 一个动作要测，却只是个假梯度。
**Alternatives**：①保留 `prefer_cheap_fallback` 中间档 + 单价排序——被否（评审定稿），常态不省钱、语义偏移、假梯度；②若将来确需有意义的中间档，**封顶 `max_tokens`（每次都省）比重排 fallback 实在**，但会截断回复有质量风险，v1.0 不做（见 Open Questions）。

## Risks / Trade-offs

- [成本感知误降级损伤质量] → 缺省关闭（headroom=None / 开关关即 `normal`），仅在运维显式配置阈值后启用；`degrade_target` 默认 None，未显式配置时 degrade 档不可用、退回 `normal`（不擅自降级），杜绝「开关一开复杂任务悄悄降到便宜模型」的质量悬崖；运维显式指定 target 时可指定一个仍可接受质量的便宜 route。spec 用 scenario 覆盖「缺省不干预」「预算充裕不降级」「未配 target 时 degrade 退回 normal」。
- [AR18 尚在 propose、`headroom()` 契约未冻结] → 本 change 仅依赖 AR18 暴露的「一个 `cost_usd` 剩余比例标量 + 触发层名」这一最小契约（D1，`BudgetHeadroom` 类型与 `headroom()` 生产者归 AR18），AR18 内部实现变化不影响；归档顺序建议 AR18（`cost-budget-control`）先于本 change，使 `headroom()` 就位。无 AR18 时 headroom 恒为 None，本 change 旁路。
- [降级与请求级 `override` 的优先级冲突] → 显式 `override`（请求级强制 model）优先级最高，在降级之后合并（D4），运维强制指定的 model 不被成本感知覆盖；spec 覆盖「override 优先于降级」。
- [`degrade_target` 配错为不存在的 task_type] → 复用 `model_router` 既有 `routes.get(target, routes["default"])` 兜底（未知 task_type 回退 default），不抛错但记录警告；不静默改成无意义路由。

## Open Questions

- 紧张级别是否需要纳入 `tokens` 维度（而非仅 `cost_usd`）作为降级信号？倾向 `cost_usd` 为主（成本感知语义最直接），`tokens` 列入后续增强。
- `degrade_target` 是否应支持「按原 task_type 分别配置降级目标」（如 `code` 降到 `code_cheap`、`default` 降到 `memory_extraction`），还是全局单一 target 足够 v1.0？倾向单一 target 起步。
- 成本感知决策是否需写入 trace（触发动作 + `tightest_scope` + 原/降级后 model）供运维核对降级是否符合预期？倾向需要，落点在 agent_loop 调用处。
- 两档之外将来若要有意义的中间档，应是**封顶 `max_tokens`**（每次调用都省，不像重排 fallback 仅在失败时才生效）而非重排 fallback；但封顶会截断回复有质量风险，v1.0 不做（见 D5）。
- 多档之外是否需要「软告警但不降级」档（仅记录预算紧张、不改路由）？当前用 `normal` 覆盖，列入后续。
