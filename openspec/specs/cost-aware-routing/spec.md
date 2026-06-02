# cost-aware-routing Specification

## Purpose
TBD - created by archiving change cost-aware-routing. Update Purpose after archive.
## Requirements

### Requirement: 路由据预算剩余倾向更便宜的模型

系统 SHALL 在 `model_router` 既有 task_type→provider 路由产物之上引入成本感知决策：当预算剩余进入配置的紧张阈值时，路由 MUST 倾向更便宜的模型（降级到运维显式配置的低成本目标 task_type）。成本感知 MUST NOT 改变 `model_router` 既有的 task_type 查表、fallback 链、`override` 合并语义；它只在 route 定型后**追加**一层决策。成本倾向动作收为两档：`normal`（不干预）与 `degrade`（改路由到配置的低成本目标 task_type）。

#### Scenario: 预算紧张时降级到低成本 route
- **WHEN** 预算剩余比例低于配置的降级阈值，且已显式配置降级目标 task_type
- **THEN** 路由解析改用配置的低成本目标 task_type（如把 `default` 降级到 cheap route），经既有 `routes.get` 路径取得，复用既有 fallback / override 合并

### Requirement: 消费 AR18 暴露的只读剩余快照，路由层与 agent_loop 均不重算层级

成本感知决策 SHALL 仅消费一个只读的预算剩余快照（最紧层的 `cost_usd` 剩余比例 + 触发层名）。该快照（`BudgetHeadroom` 类型）与生产它的 `headroom()` 函数均归 AR18（`agent-cost-budget`）所有，AR18 复用其五层迭代算出剩余比例。本 change 从 AR18 **import 该类型并消费其标量产出**，由调用方（agent_loop）调用 AR18 的 `headroom(...)` 取得后**按次传入** `model_router`。路由层与 agent_loop MUST NOT 自行累计、落盘、读取 AR18 的存储实现或重算层级迭代。

#### Scenario: 据剩余比例决定动作
- **WHEN** 传入剩余比例为 0.05（远低于降级阈值）的预算快照，且已配置降级目标
- **THEN** 成本感知决策判定为「降级」，并据快照携带的触发层名供 trace 归因

#### Scenario: 路由层与 agent_loop 不重算层级
- **WHEN** 成本感知决策执行
- **THEN** 决策仅依据 AR18 `headroom()` 产出的只读剩余快照，不查询任何数据库、不读取 AR18 累计表、不在路由层或 agent_loop 重复 AR18 的五层迭代

### Requirement: 未传入剩余信号或预算充裕时路由与现状等价

未传入预算剩余信号（信号为 None）或成本感知开关关闭时，路由 SHALL 与现状**逐字节等价**：task_type 查表、`model`、`fallbacks` 链、`override` 合并、client 构造均不变。预算剩余充裕（高于所有阈值）时 MUST NOT 干预路由。缺省配置 MUST 使成本感知整链不干预（向后兼容）。

#### Scenario: 无剩余信号旁路
- **WHEN** 调用路由入口而不传入预算剩余信号
- **THEN** 返回的 route 与现状完全一致（主 model、fallback 链顺序、override 合并结果均不变）

#### Scenario: 预算充裕不降级
- **WHEN** 传入剩余比例为 0.9（高于所有阈值）的预算快照
- **THEN** 成本感知决策判定为「不干预」，route 保持不变

#### Scenario: 开关关闭时不干预
- **WHEN** 成本感知开关为缺省（关闭）
- **THEN** 无论剩余信号如何，路由均不被调整

### Requirement: 紧张级别到成本动作的映射可配置

预算紧张级别到成本倾向动作（两档：不干预 / 降级到低成本 route）的映射 SHALL 经配置阈值声明，降级阈值与降级目标 task_type 均可配置。降级目标 task_type 缺省为 None（不给默认便宜 route）；成本感知启用但**未显式配置降级目标时，`degrade` 档不可用，决策 SHALL 退回 `normal`**（不擅自降级，避免质量悬崖）。配置缺省时 SHALL 使整链不干预。非法配置（如降级目标为不存在的 task_type）MUST NOT 静默产生无意义路由：SHALL 复用 `model_router` 既有未知 task_type 回退 `default` 的兜底并记录，不吞异常。

#### Scenario: 阈值与降级目标可配置
- **WHEN** 配置降级阈值与降级目标 task_type
- **THEN** 成本感知决策据配置的阈值判定动作，降级时改用配置的目标 task_type

#### Scenario: 未配置降级目标时 degrade 退回 normal
- **WHEN** 成本感知已启用且预算剩余低于降级阈值，但未显式配置降级目标 task_type（缺省 None）
- **THEN** 决策退回 `normal`，路由不被调整（不擅自把任务降级到某个默认便宜模型）

#### Scenario: 降级目标为未知 task_type 时安全兜底
- **WHEN** 配置的降级目标 task_type 在路由表中不存在
- **THEN** 复用 `model_router` 既有「未知 task_type 回退 default」兜底并记录该问题，不抛未捕获异常、不静默改成无意义路由

### Requirement: 请求级 override 优先级高于成本感知降级

显式请求级 `override`（如强制 `model`）SHALL 在成本感知降级之后合并，优先级最高。运维显式指定的 model MUST NOT 被成本感知降级覆盖。

#### Scenario: override 覆盖降级结果
- **WHEN** 同时传入触发降级的预算快照与一个强制 `model` 的 `override`
- **THEN** 最终 route 的 `model` 为 `override` 指定的值，成本感知降级不覆盖请求级强制指定
