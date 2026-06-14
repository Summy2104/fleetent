# mcp-session-continuity Specification

## Purpose
TBD - created by archiving change mcp-session-management. Update Purpose after archive.
## Requirements
### Requirement: 调用失败时懒重连重试一次

当持有 SDK `ClientSession` 的 MCP 服务在 `tools/call` 或 `tools/list` 因会话/连接级失效(SDK 抛出连接错误或会话失效)时,平台 SHALL 就地重开该服务的 `ClientSession`(重新经对应 SDK transport 建立 + `initialize`)并对原请求重试一次。重建成功时调用方 MUST 无感知地拿到正常结果。重开前 SHALL 先向旧会话宿主发出关闭信号并限时等待其退出(关闭失败仅记录日志,不阻断重开)——重连 MUST NOT 遗留孤儿宿主或未关闭的传输连接。该懒重连取代旧的"手写 404/marker 检测 + 重新 initialize"机制。

#### Scenario: 会话失效后懒重连并取得结果
- **WHEN** 某 `http` 服务的 `tools/call` 因会话/连接失效抛错
- **THEN** 平台就地重开该服务 `ClientSession`、以新会话重试该调用,调用方拿到与会话有效时一致的工具结果

#### Scenario: 注册期失效同样懒重连
- **WHEN** 某服务在 `tools/list`(注册阶段)因会话/连接失效抛错
- **THEN** 平台重开 `ClientSession` 后重试列举,工具仍以 `{server_id}__{tool_name}` 命名空间正常注册

#### Scenario: 重连不泄漏旧宿主
- **WHEN** 懒重连发生
- **THEN** 旧会话宿主 task 在限时内结束(或被取消兜底),注册表中不存在指向旧会话的残留条目

### Requirement: 懒重连至多一次,仍失败则降级

懒重连 SHALL 对同一请求至多发生一次。重开并重试后若仍失败,平台 MUST NOT 继续重连,而是将该服务标记为不可用并返回降级结果(「服务暂时不可用」),不崩溃 agent loop。

#### Scenario: 连续失败不无限重连
- **WHEN** 某请求懒重连并重试后仍失败
- **THEN** 平台不再发起第二次重连,将该服务标记不可用并返回降级结果

### Requirement: 会话生命周期随 SDK ClientSession 按服务隔离持有

每个服务的 `ClientSession`(及其底层传输连接)SHALL 由一个**专属会话宿主 task** 全权拥有:宿主 task 内依次 enter SDK transport 上下文与 `ClientSession` 上下文、完成 `initialize`、驻留等待关闭信号、并在**同一 task 内** exit 两个上下文(满足 anyio cancel scope 的 task 亲和性约束,三种 transport——stdio / sse / streamable-http——统一适用)。宿主句柄存于 `_session_hosts[(scope, server_id)]`,live `ClientSession` 仍存于 `_active_sessions[(scope, server_id)]` 供调用方复用;不同服务互不影响。会话生命周期 MUST NOT 挂在模块级共享 `AsyncExitStack` 或任何"打开者与关闭者可能不同 task"的持有结构上;跨 task 只传递会话句柄,生命周期操作(打开/关闭)只发生在宿主 task 内。

#### Scenario: 会话随宿主 task 持有且同 task 收尾
- **WHEN** 某服务注册成功,随后由另一个 task(如关停流程)请求关闭该会话
- **THEN** transport 与 `ClientSession` 的 enter/exit 均发生在宿主 task 内,关闭不抛跨 task cancel scope 异常,`_active_sessions[(scope, id)]` 中该宿主被移除

#### Scenario: 打开失败按既有注册失败路径处理
- **WHEN** 宿主 task 在建立 transport 或 `initialize` 阶段失败
- **THEN** 失败异常传播给打开调用方(沿用既有注册失败/降级语义),不留下驻留宿主

### Requirement: 关停时释放所有会话宿主

运行时关停时 SHALL 调用 `aclose_all()` 并发释放所有会话宿主:向每个宿主发出关闭信号并等待其在自身 task 内完成 transport / `ClientSession` 退出(由 SDK 负责会话端点的 `DELETE` / 连接关闭);单个宿主超过关闭时限(默认 5 秒,可注入)SHALL 被取消兜底。该释放为 best-effort:单个会话关闭失败 MUST 仅记录日志,不得抛出、不得阻断其余宿主的关闭、不得改变进程退出码。`aclose_all()` SHALL 接入两条关停链:agent 进程的优雅排水流程(在飞 run 排干**之后**、进程退出**之前**),以及 platform 服务的 lifespan shutdown。

#### Scenario: 关停释放所有会话
- **WHEN** agent 进程优雅排水完成(在飞 run 归零或超时)
- **THEN** `aclose_all()` 被调用,所有宿主在各自 task 内退出,进程随后正常退出

#### Scenario: 单个宿主关闭失败不阻断
- **WHEN** 某宿主关闭时其 transport 退出抛出异常
- **THEN** 该异常仅产生一条 warning 日志,其余宿主照常关闭,关停流程继续且退出码不变

#### Scenario: 卡死宿主被限时取消
- **WHEN** 某宿主在关闭时限内未退出
- **THEN** 该宿主 task 被取消兜底,关停流程在有界时间内完成

