# mcp-health-reconnect Specification

## Purpose
TBD - created by archiving change mcp-health-reconnect. Update Purpose after archive.
## Requirements
### Requirement: 连接健康状态按服务隔离

平台 SHALL 为每个已注册 MCP 服务维护连接健康标记(健康 / 不可用),按服务实例隔离持有,MUST NOT 置于模块级可变全局状态。该标记记录"上次已知是否不可用",喂给 schema 可见性过滤(不可用服务的工具对模型隐藏)。某服务的健康标记变化 MUST NOT 影响其他服务。

#### Scenario: 单服务不可用不影响其他服务
- **WHEN** 一个 MCP 服务被标记不可用而另一服务健康
- **THEN** 不可用服务的工具对模型隐藏 / 调用返回不可用信号,健康服务的工具正常

### Requirement: 调用失败触发懒重连,成功恢复健康

当 MCP 服务的工具调用因连接级断连(SDK 抛连接错 / stdio 子进程死)失败时,平台 SHALL 就地重开该服务 `ClientSession` 并重试一次(懒重连)。重开成功 MUST 将其健康标记恢复为健康,工具自动恢复可调用;重开仍失败 MUST 将其标记为不可用。平台 MUST NOT 在后台周期性探活或维护指数退避重连循环。

#### Scenario: 断连调用懒重连成功后恢复
- **WHEN** 某服务工具调用因断连失败,懒重连重开成功
- **THEN** 平台将其恢复健康,该次调用返回正常结果,后续调用照常

#### Scenario: 懒重连失败标记不可用
- **WHEN** 某服务工具调用断连且懒重连重开仍失败
- **THEN** 平台将其标记不可用,返回降级结果

### Requirement: 不可用期间工具调用返回不可用信号

当服务处于不可用状态时,对其工具的调用 MUST 返回明确的「服务暂时不可用」结果,而非裸抛异常或静默卡住,且 MUST NOT 阻断其他服务工具或当前对话。

#### Scenario: 不可用服务工具返回暂时不可用
- **WHEN** agent 调用一个不可用服务的工具
- **THEN** 该调用返回「服务暂时不可用」结果,不抛异常、不卡住,其他服务不受影响

