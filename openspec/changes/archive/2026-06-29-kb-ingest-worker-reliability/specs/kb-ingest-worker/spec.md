## ADDED Requirements

### Requirement: Worker 存活可观测

`fleetent kb worker` SHALL 周期性写入存活信号(heartbeat),使控制面能判定当前是否存在活跃 worker。存活判定 SHALL 基于一个可配置的过期阈值:在阈值内有 heartbeat(或近期 job claim)记为活跃,否则记为无活跃 worker。该信号经 `db.py` 边界持久化,worker SHALL NOT 为此 `import fleetent.platform.*`。

#### Scenario: worker 运行时写入存活信号
- **WHEN** `fleetent kb worker` 在跑
- **THEN** 系统在过期阈值内可观测到该 worker 的存活信号

#### Scenario: 无 worker 时存活信号过期
- **WHEN** 没有任何 `fleetent kb worker` 在跑且超过过期阈值
- **THEN** 控制面判定为"无活跃 worker"

### Requirement: 非终态 ingest 状态区分降级与处理中

admin ingest / sync 端点在返回非终态(未 done / failed)结果时 SHALL 区分两种情况,且 SHALL NOT 在无活跃 worker 时返回与正常排队无差别的裸 `pending`:
- 有活跃 worker:返回 `in_progress` / `queued` 等表示 job 正常排队或处理中的状态;
- 无活跃 worker:返回明确的 `degraded`(或等价标记),表明 job 不会推进、需要拉起 worker。

#### Scenario: 有活跃 worker 时返回处理中
- **WHEN** admin 触发 import 或 sync,job 入队,且存在活跃 worker,但在超时窗口内未完成
- **THEN** 端点返回 job id + `in_progress` / `queued` 状态

#### Scenario: 无活跃 worker 时返回降级
- **WHEN** admin 触发 import 或 sync,job 入队,但无活跃 worker
- **THEN** 端点返回 job id + `degraded`(或等价明确标记)
- **AND** 响应可据此区分"worker 未运行"而非"job 正常排队中"

#### Scenario: 不引入绕过队列的执行
- **WHEN** 检视实现
- **THEN** 仍只有 `fleetent kb worker` 消费队列,未为可观测性新增任何在控制面进程内同步跑 ingest 的路径
