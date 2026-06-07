# agent-input-steering Specification

## Purpose
TBD - created by archiving change agent-input-steering. Update Purpose after archive.
## Requirements
### Requirement: 运行中按 steering_mode 分派新消息

当某 session 已有进行中的 run 时，IM 网关 SHALL 在抢 session 锁之前按该 agent 的 `steering_mode` 分派新到达消息，而非一律阻塞成新 turn：`steer`（默认）把消息注入进行中的 run；`interrupt` 取消当前 run；`queue` 维持既有串行（处理完上一条再处理本条）。无进行中 run 时 MUST 走正常新 turn。`steer` 投递失败（无活跃 run 的竞态、或邮箱已满）时 MUST 回退为正常新 turn 而非丢失消息。

#### Scenario: 默认 steer 注入进行中任务
- **WHEN** 某 session 有进行中 run，`steering_mode="steer"`，到达一条新消息
- **THEN** 该消息被投递进进行中 run 的待注入邮箱，不另起新 run，向用户回执"已发给当前任务"

#### Scenario: interrupt 取消当前 run
- **WHEN** 某 session 有进行中 run，`steering_mode="interrupt"`，到达新消息
- **THEN** 当前 run 的取消令牌被触发，向用户回执已请求停止

#### Scenario: 无进行中 run 走正常新 turn
- **WHEN** 某 session 无进行中 run
- **THEN** 消息按既有路径（持锁、load、append、run）处理为新 turn

### Requirement: steer 在轮间注入进行中的 run

agent loop SHALL 在每个 turn 的边界（压缩之后、消息卫生 sanitize 之前）消费该 session 待注入的 steered 消息，作为 `user` 消息追加进序列后再发往 LLM。注入 MUST 只发生在轮间检查点，MUST NOT 在工具调用与其结果之间插入（以免破坏消息序列契约）；无 session 或无活跃 steering 登记时 MUST 为 no-op（既有调用行为不变）。

#### Scenario: 进行中 run 在下一轮看到注入的消息
- **WHEN** 一条消息在 run 进行中被 steer 注入，且 run 仍有下一个 turn
- **THEN** 下一个 turn 发往 LLM 的消息序列包含该注入的 user 消息

#### Scenario: 无 steering 登记时 loop 行为不变
- **WHEN** run 无 session_id 或该 session 无活跃 steering 登记
- **THEN** 轮间消费为 no-op，loop 行为与未引入本能力时一致

### Requirement: steering 行为经 agent.yaml 配置

steering 行为 SHALL 由每-agent 配置驱动：`steering_mode`（`steer` / `queue` / `interrupt`，默认 `steer`）与 `steering_max_pending`（待注入邮箱上限，默认 8）。配置 MUST 经 `agent.yaml`（`AgentFile` → `GovernanceConfig`）解析，MUST NOT 依赖 platform。邮箱满时新 steer MUST 被拒（回退正常新 turn），不得无界堆积。

#### Scenario: 默认配置为 steer
- **WHEN** agent 未显式配置 steering_mode
- **THEN** 运行中转向按 `steer` 处理

#### Scenario: 邮箱满时拒绝并回退
- **WHEN** 待注入邮箱已达 `steering_max_pending` 上限，再来一条 steer
- **THEN** 该 steer 被拒（不入队），caller 回退为正常新 turn

