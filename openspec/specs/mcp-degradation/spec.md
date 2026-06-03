# mcp-degradation Specification

## Purpose
TBD - created by archiving change mcp-degradation. Update Purpose after archive.
## Requirements

### Requirement: 统一可用性判定整合连接健康与认证不可用两正交态

平台 SHALL 提供单点判定「某 MCP 服务的工具此刻是否对 AI 可用」，该判定 MUST 整合两个正交维度：连接级健康（MCP3 的 `HealthState`，仅 `healthy` 视为连接可用）与认证级不可用（MCP5 的认证不可用标志，仅对 `oauth2` 服务生效）。当且仅当连接健康**且**认证可用时，服务工具才判定为可用；任一维度不可用，服务工具整体不可用。该判定 MUST 按服务实例读取，MUST NOT 引入新的模块级可变全局状态，且 MUST NOT 改变 MCP3 健康态或 MCP5 认证标志各自的语义。

#### Scenario: 两态均健康判定可用
- **WHEN** 某服务连接处于 `healthy` 且未被标记认证不可用
- **THEN** 该服务工具判定为可用

#### Scenario: 连接降级即判定不可用
- **WHEN** 某服务连接处于 `degraded` 或 `unavailable`（无论认证态）
- **THEN** 该服务工具判定为不可用

#### Scenario: 认证不可用即判定不可用
- **WHEN** 某 `oauth2` 服务连接处于 `healthy` 但被标记为认证不可用
- **THEN** 该服务工具判定为不可用（认证态正交于连接态，独立致其不可用）

#### Scenario: 非 oauth2 服务无认证维度
- **WHEN** 某 `none` 或 `api_key` 服务连接处于 `healthy`
- **THEN** 该服务工具判定为可用（认证不可用维度仅对 `oauth2` 生效）

### Requirement: 不可用服务的工具从 AI 可见 schema 临时摘除并在恢复后重新可见

当某 MCP 服务判定为不可用时，其工具 SHALL 从提供给 LLM 的工具 schema 列表中临时摘除，使 AI 不再看到这些工具。摘除 MUST 为过滤视图，MUST NOT 删除工具注册项；服务恢复（连接重连成功或认证不可用标志被清除）后，其工具 SHALL 自动重新出现在 schema 列表中，无需重新注册。非 MCP 工具的 schema MUST NOT 受影响。

#### Scenario: 不可用服务工具不出现在 schema
- **WHEN** 某 MCP 服务判定为不可用，请求 AI 可见的工具 schema 列表
- **THEN** 该服务的工具 schema 不出现在列表中，其他服务与非 MCP 工具的 schema 正常出现

#### Scenario: 服务恢复后工具重新可见
- **WHEN** 一个先前不可用、其工具已被摘除的服务恢复为可用（连接恢复 healthy 且认证可用）
- **THEN** 该服务的工具 schema 自动重新出现在列表中，无需重新注册其工具

#### Scenario: 摘除不删除工具注册项
- **WHEN** 某服务工具因不可用被摘除出 schema
- **THEN** 该工具的注册项仍存在（摘除为过滤视图），恢复后同一注册项重新可见，无副作用

### Requirement: 降级模式可配置为 degrade / strict / silent

平台 SHALL 支持按服务配置降级模式，取值为 `degrade`（默认）/ `strict` / `silent`。未配置时 MUST 回退默认 `degrade`。配置值非法时系统 MUST NOT 静默接受，SHALL 记录后回退 `degrade`，不得吞异常。

- `degrade`：服务不可用时摘除该服务工具，其余服务与当前对话正常进行。
- `strict`：服务不可用时当前 agent 运行 MUST 以明确错误终止，MUST NOT 静默继续；其终止影响范围 SHALL 限定于绑定该服务的 agent 运行，MUST NOT 阻断整个平台或其他 agent。此处「agent 绑定某服务」定义为：该 agent 的 `allowed_tools` 白名单（fnmatch）覆盖该服务的 `{server_id}__*` 工具命名空间（即二者相交）。strict 终止 MUST 仅作用于 `allowed_tools` 覆盖了该 strict-且-不可用服务工具的 agent；`allowed_tools` 与该服务 `{server_id}__*` 命名空间不相交的 agent MUST NOT 受其 strict 终止影响。
- `silent`：与 `degrade` 同样摘除工具，但 MUST 仅记录日志，MUST NOT 产生面向用户/外部的降级通知。silent 与 `degrade` 的唯一差异是「不发面向用户/外部的降级通知」；该通知通道本 change 不实现（属 observability 域，见 design Non-Goals），因此在通知通道落地之前 `silent` 的可观察行为等同于 `degrade`（均摘除工具并记录日志）。silent 为将来通知能力的前向声明模式。

#### Scenario: degrade 模式摘除工具其余正常
- **WHEN** 一个 `degrade` 模式的服务不可用，另一服务保持可用
- **THEN** 不可用服务的工具被摘除出 schema，可用服务的工具与当前对话正常进行

#### Scenario: strict 模式不可用即终止 agent
- **WHEN** 一个 `strict` 模式的服务不可用，且当前 agent 绑定了该服务（其 `allowed_tools` 覆盖该服务 `{server_id}__*` 工具命名空间）
- **THEN** 当前 agent 运行以明确错误终止，不静默继续；其他 agent 与平台不受影响

#### Scenario: strict 服务不可用但 agent 未绑定不终止
- **WHEN** 一个 `strict` 模式的服务不可用，但当前 agent 的 `allowed_tools` 与该服务 `{server_id}__*` 工具命名空间不相交（未绑定该服务）
- **THEN** 当前 agent 运行不因该服务的 strict 终止而中断

#### Scenario: silent 模式摘除工具仅记录日志
- **WHEN** 一个 `silent` 模式的服务不可用
- **THEN** 该服务工具被摘除出 schema，平台记录日志但不产生面向用户/外部的降级通知（通知通道本 change 不实现，故在其落地前 silent 的可观察行为等同于 `degrade`）

#### Scenario: 未配置时默认 degrade
- **WHEN** 某服务未声明降级模式且不可用
- **THEN** 按默认 `degrade` 行为处理（摘除工具，其余正常）

#### Scenario: 非法降级模式回退默认
- **WHEN** 某服务配置了不在 `degrade`/`strict`/`silent` 枚举内的降级模式值
- **THEN** 系统记录该问题并回退默认 `degrade`，不静默接受非法值、不吞异常

### Requirement: 启动失败降级与运行时降级对 AI 表现一致

某 MCP 服务在启动注册时连接失败 SHALL 等同于不可用态：平台 MUST 正常启动、不被该服务的启动失败阻断，且该服务的工具 MUST NOT 出现在 AI 可见的 schema 列表中（与运行时降级摘除效果一致）。启动失败服务 SHALL 受与运行时同一套降级模式约束：`silent` 仅记录日志；`strict` 服务启动失败 MUST NOT 阻断整个平台启动，仅使绑定该服务的 agent 运行以明确错误终止。

#### Scenario: 启动失败服务工具不可见且平台正常启动
- **WHEN** 配置了两个 MCP 服务，其中一个启动注册即连接失败
- **THEN** 平台正常启动，失败服务的工具不出现在 AI 可见 schema，另一服务工具正常可见

#### Scenario: strict 服务启动失败仅影响其绑定 agent
- **WHEN** 一个 `strict` 模式的服务启动注册失败
- **THEN** 平台仍正常启动、其他服务与 agent 不受影响，仅绑定该 strict 服务的 agent 运行以明确错误终止

### Requirement: 降级期工具调用仍安全返回不可用结果

即使在工具被摘除出 schema 与一次调用发生之间存在竞态，对一个不可用服务工具的调用 MUST 仍返回明确的不可用结果（连接级返回「服务暂时不可用」、认证级返回「认证不可用」），MUST NOT 进入实际网络请求或子进程调用，MUST NOT 裸抛异常或静默卡住，且 MUST NOT 影响其他服务工具或当前对话。

#### Scenario: 竞态调用不可用服务工具仍安全返回
- **WHEN** 某服务工具已被摘除，但 LLM 基于摘除前的 schema 仍发起了对该工具的调用
- **THEN** 该调用直接返回明确的不可用结果，不进入真实网络/子进程、不抛异常、不卡住，其他服务工具不受影响
