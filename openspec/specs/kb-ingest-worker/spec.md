# kb-ingest-worker Specification

## Purpose
TBD - created by archiving change kb-worker. Update Purpose after archive.
## Requirements
### Requirement: kb-worker 是 ingest 队列的唯一消费者

系统 SHALL 提供长驻进程 `fleetent kb-worker`,作为 `kb_ingest_jobs` 队列的**唯一消费者**:循环 claim(原子)pending job → 调 `knowledge_base.ingest` 核执行摄取 → mark done;失败则 mark failed + retry(至上限)。KB 内容写入 SHALL 只发生在 worker 调核的路径(**单一写入方**)。worker SHALL 经 `db.py` 边界访问队列,SHALL NOT `import fleetent.platform.*`。

#### Scenario: worker drain 队列并写 KB

- **WHEN** 队列有 pending job 且 `fleetent kb-worker` 在跑
- **THEN** worker claim 该 job、调 ingest 核完成摄取、写 KB、置 job done

#### Scenario: 失败重试

- **WHEN** worker 处理某 job 抛错且 attempts 未达上限
- **THEN** job 回 pending 等重试;达上限置终态 failed

#### Scenario: 单一写入方

- **WHEN** 检视所有写 KB 内容的代码路径
- **THEN** 仅 worker 调核这一条;生产无其它写 KB 内容的入口

### Requirement: 生产无绕过队列的 ingest 路径

移除 `kb-ingest-queue` 引入的过渡内联 drain 后,生产 SHALL NOT 存在任何绕过队列/worker 的 ingest 执行路径。直接调 `knowledge_base.ingest` 核 SHALL 仅出现在测试(in-process)。admin sync SHALL 入队 + 轮询 job 状态(同步体验、worker 异步执行;超时后返回 job id + 当前状态,不无限阻塞)。

#### Scenario: 过渡 drain 已移除

- **WHEN** 检视代码
- **THEN** 不存在 `kb-ingest-queue` 阶段的临时内联 drain;消费只经 `fleetent kb-worker`

#### Scenario: admin sync 入队 + 轮询

- **WHEN** admin 触发 sync(execute)
- **THEN** 端点入队 → 轮询 job 至 done/failed 返回结果;若超时则返回 job id + 当前状态

### Requirement: kb-worker 从专属 .env 加载自身配置

`fleetent kb-worker` 启动 SHALL 从 `$FLEETENT_HOME/kb-worker/.env` 加载自身配置(经 `load_dotenv(override=False)`:文件不存在静默跳过;进程已有环境变量优先于文件值)。自身配置 SHALL 含:队列连接、数据底座连接、embedder 配置、Vault 接入。`FLEETENT_HOME` SHALL 经进程环境提供(定位该 `.env` 的前提,不可经该 `.env` 设置)。

#### Scenario: 从 .env 加载

- **WHEN** `$FLEETENT_HOME/kb-worker/.env` 含队列/底座/embedder/Vault 接入配置,且未在进程环境设置
- **THEN** worker 从该文件读取并成功启动

#### Scenario: 进程环境优先

- **WHEN** 某项同时存在于进程环境与该 `.env`
- **THEN** 采用进程环境的值(override=False)

#### Scenario: 文件缺失回退进程环境

- **WHEN** 该 `.env` 不存在
- **THEN** 加载步骤静默跳过,配置仅来自进程环境

### Requirement: connector 配置不在 worker 自身配置内

worker 自身配置 SHALL 只含部署级静态连接信息(队列/底座/embedder/Vault 接入)。connector 配置(源地址/参数/凭据)SHALL NOT 出现在 worker 自身配置文件中——它由 Platform 注册表 + Vault 持有,随 job 下发。

#### Scenario: worker 配置不含 connector

- **WHEN** 检视 `kb-worker.env.example` 与 worker 配置加载
- **THEN** 不含任何具体 connector 的源地址/参数/凭据;这些经 job 下发

### Requirement: Worker 存活可观测

`fleetent kb-worker` SHALL 周期性写入存活信号(heartbeat),使控制面能判定当前是否存在活跃 worker。存活判定 SHALL 基于一个可配置的过期阈值:在阈值内有 heartbeat(或近期 job claim)记为活跃,否则记为无活跃 worker。该信号经 `db.py` 边界持久化,worker SHALL NOT 为此 `import fleetent.platform.*`。

#### Scenario: worker 运行时写入存活信号
- **WHEN** `fleetent kb-worker` 在跑
- **THEN** 系统在过期阈值内可观测到该 worker 的存活信号

#### Scenario: 无 worker 时存活信号过期
- **WHEN** 没有任何 `fleetent kb-worker` 在跑且超过过期阈值
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
- **THEN** 仍只有 `fleetent kb-worker` 消费队列,未为可观测性新增任何在控制面进程内同步跑 ingest 的路径

