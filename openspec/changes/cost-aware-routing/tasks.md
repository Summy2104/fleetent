## 1. 前置核实（实现前的事实确认，无代码改动）

- [x] 1.1 核实 `src/fleetent/model_router.py`（MR1）对外契约：`RouteConfig`（`base_url/model/api_key_env/max_tokens/fallbacks/params`）、`RouteOverride` 字段合并（`_apply_override`，含「设 model 不给 fallbacks 即清空链」）、`_load_routes()` 查表（`routes.get(task_type, routes["default"])`）、`get_(async_)client_and_config(task_type, override)` 入口与 client 每次新建——确认本 change 仅在 route 定型后旁路追加、不改其语义
- [x] 1.2 核实兄弟 change `cost-budget-control`（AR18，`agent-cost-budget`）暴露的 `BudgetHeadroom` 类型与 `headroom(session_id, user_id, agent_id) -> BudgetHeadroom` 生产者：确认本 change 只 import 该类型、消费一个 `cost_usd` 剩余比例标量（最小契约），不耦合 AR18 存储、不重算层级迭代
- [x] 1.3 核实 `config.py` `Settings` 字段惯例（env-first、缺省关闭向后兼容）与 yaml 路径 monkeypatch 隔离惯例

## 2. 消费 AR18 的预算剩余快照（cost_aware_routing.py）

- [x] 2.1 Write failing tests：从 AR18（`cost-budget-control`）import `BudgetHeadroom` 类型并消费——构造携带 `cost_remaining_ratio: float ∈ [0,1]` 与 `tightest_scope: str | None` 的快照（全无上限时比例为 1.0=充裕），断言本模块仅消费、不在 `cost_aware_routing.py` 定义该类型。运行 `uv run pytest -x -q` 看到红
- [x] 2.2 核实/import AR18 的 `BudgetHeadroom` 并消费（不在本模块定义该类型、不在 agent_loop 自算 headroom），看到绿

## 3. 紧张级别→动作策略（cost_aware_routing.py / CostAwareRoutingPolicy）

- [x] 3.1 Write failing tests：`CostAwareRoutingPolicy.decide(headroom)` 两档据阈值返回 `normal`/`degrade`（剩余低于 degrade 阈 → degrade；高于阈值 → normal；headroom=None → normal）；`degrade_target` 为 None（未显式配置）时即使剩余低于阈值也退回 `normal`（不擅自降级）。看到红
- [x] 3.2 Implement `CostAwareRoutingPolicy`（`degrade_below` 阈值 + `degrade_target: str | None`（默认 None）+ `decide` 两档），看到绿
- [x] 3.3 Write failing tests：`from_settings(settings)` 据缺省配置构造出「整链不干预」的 policy（开关关 / 阈值缺省 / `degrade_target` 缺省 None → 恒 normal）。看到红
- [x] 3.4 Implement `from_settings`（缺省关闭、`degrade_target` 缺省 None、向后兼容），看到绿

## 4. 动作落到 model_router 既有产物（cost_aware_routing.py）

- [x] 4.1 Write failing tests：`normal` 时 route 逐字节不变（主 `model` / `fallbacks` 链顺序均不动）。看到红
- [x] 4.2 Implement `normal` 旁路（返回原 route 不变），看到绿
- [x] 4.3 Write failing tests：`degrade` 时路由解析改用 `degrade_target` task_type，经既有 `routes.get(target, routes["default"])` 取得；`degrade_target` 为未知 task_type 时回退 default 并记录、不抛未捕获异常。看到红
- [x] 4.4 Implement degrade 改 task_type 解析（复用既有查表与未知回退兜底），看到绿

## 5. model_router 接入点（旁路兼容）

- [x] 5.1 Write failing tests：`get_(async_)client_and_config` 新增可选 `headroom`（及可注入 policy）；`headroom is None` 时路由与现状逐字节等价（主 model / fallback 顺序 / override 合并结果不变）。client 构造 mock。看到红
- [x] 5.2 Implement：在 `_apply_override` 后、client 构造前接入决策，None 旁路（现状路径），看到绿
- [x] 5.3 Write failing tests：触发 `degrade` 的 headroom 使路由降级到低成本 route；预算充裕（高于全部阈值）不降级。看到红
- [x] 5.4 Implement 紧张时降级 / 充裕时旁路接线，看到绿
- [x] 5.5 Write failing test：同时传入触发降级的 headroom 与强制 `model` 的 `override`，最终 route 的 `model` 为 override 值（override 在降级之后合并、优先级最高）。看到红
- [x] 5.6 Implement override 后于降级合并的次序，看到绿

## 6. Settings 成本感知字段（config.py）

- [x] 6.1 Write failing tests：`Settings` 新增成本感知开关 + 降级阈值 + `degrade_target` 字段（`degrade_target` 默认 None），默认使整链不干预（开关关）。看到红
- [x] 6.2 Implement 新增字段（env-first，缺省关闭、`degrade_target` 缺省 None，向后兼容），看到绿

## 7. 收尾

- [x] 7.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`），无回归
- [x] 7.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿
- [x] 7.3 `uv run mypy src` 无新增错误
