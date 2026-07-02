# kb-ingest-worker Specification

## Purpose
TBD - created by archiving change kb-worker. Update Purpose after archive.
## Requirements
### Requirement: kb-worker 是 ingest 队列的唯一消费者

系统 SHALL 提供长驻 worker(随 **standalone KB 服务**运行),作为 **KB 服务本地** ingest 队列的**唯一消费者**,处理 connector sync 与 `extraction` job:循环 claim(原子)pending job → 按 job_type 调 `knowledge_base.ingest` 核执行摄取,或调 `run_entity_extraction` 执行抽取 → mark done;失败则 mark failed + retry(至上限)。KB 内容与图谱写入 SHALL 只发生在 worker 调核的路径(**单一写入方**)。worker SHALL 经 `db.py` 边界访问**本地**队列,SHALL NOT `import fleetent.platform.*`。平台启动、drain management.db 队列的 kb-worker 接线**已退役**。

#### Scenario: worker drain 本地队列并写 KB

- **WHEN** KB 本地队列有 pending job 且 worker 在跑
- **THEN** worker claim 该 job、调核完成摄取/抽取、写 KB、置 job done
- **AND** 不读写 management.db

#### Scenario: worker 消费 extraction job

- **WHEN** 队列有 pending `extraction` job 且 `fleetent kb worker` 在跑
- **THEN** worker claim 该 job、对目标 document 调 `run_entity_extraction` 写 entities/mentions/relations、置 job done

#### Scenario: 失败重试

- **WHEN** worker 处理某 job 抛错且 attempts 未达上限
- **THEN** job 回 pending 等重试;达上限置终态 failed

#### Scenario: 单一写入方

- **WHEN** 检视所有写 KB 内容与图谱的代码路径
- **THEN** 仅 worker 调核这一条;生产无其它写 KB 内容 / 图谱的入口

### Requirement: 生产无绕过队列的 ingest 路径

移除 `kb-ingest-queue` 引入的过渡内联 drain 后,生产 SHALL NOT 存在任何绕过队列/worker 的 ingest 执行路径。直接调 `knowledge_base.ingest` 核 SHALL 仅出现在测试(in-process)。admin sync SHALL 入队 + 轮询 job 状态(同步体验、worker 异步执行;超时后返回 job id + 当前状态,不无限阻塞)。

#### Scenario: 过渡 drain 已移除

- **WHEN** 检视代码
- **THEN** 不存在 `kb-ingest-queue` 阶段的临时内联 drain;消费只经 `fleetent kb worker`

#### Scenario: admin sync 入队 + 轮询

- **WHEN** admin 触发 sync(execute)
- **THEN** 端点入队 → 轮询 job 至 done/failed 返回结果;若超时则返回 job id + 当前状态

### Requirement: kb-worker 从专属 .env 加载自身配置

`fleetent kb worker` 默认**单机多租户**,启动 SHALL 从**本机服务级 config** `$FLEETENT_HOME/kb-service.yaml` 加载构造配置(队列/底座/embedding/extraction/共享 service key)。worker SHALL **轮询本机所有在册租户**的 per-tenant 队列(`tenants/<t>/kb/data/kb_ingest_queue.db`,租户经扫 `tenants/*/kb/data/` 发现),认领 job 后按 job.tenant_id 经 `TenantRouter` 写该租户 KB,并**按需加载该租户** connector 配置与 secret(`tenants/<t>/kb/connectors.yaml` + `.env`,connector `credential_ref` 本地解析——仅 connector_sync 类 job 需要)。worker MAY 经 `--tenant <id>` 锁单租户(只从该租户 kb home 加载并只 drain 其队列)。旧的 tenant-less legacy 兜底与 `kb worker init-config` / `kb-worker/.env` 模型仍**已退役**。

#### Scenario: worker 默认多租户加载
- **WHEN** `fleetent kb worker`(默认,读本机 `$FLEETENT_HOME/kb-service.yaml`)启动
- **THEN** worker 从本机 config 取构造配置(含 embedding/共享 service key),轮询所有在册租户队列,按 job.tenant_id 写各租户 `tenants/<t>/kb/data/`
- **AND** 处理某租户 connector_sync 时按需加载该租户 `connectors.yaml` + `.env`,不加载其它租户 secret

#### Scenario: --tenant 锁单租户
- **WHEN** `fleetent kb worker --tenant T` 启动
- **THEN** 只从 `tenants/T/kb/` 加载并只 drain `tenants/T/kb/data/kb_ingest_queue.db`,不碰其它租户

#### Scenario: 旧 init-config 与 tenant-less 兜底仍退役
- **WHEN** 查看 CLI 与 worker 配置加载逻辑
- **THEN** 不提供 `fleetent kb worker init-config` / `kb-worker.env.example` / `kb-worker/.env`
- **AND** 不存在读 `$FLEETENT_HOME/kb-service/.env` 的 tenant-less legacy 兜底
- **AND** 本机服务 config 由 `fleetent kb init-config` 生成于 `$FLEETENT_HOME/kb-service.yaml`,per-tenant connector 于 `tenants/<t>/kb/connectors.yaml`

### Requirement: connector 配置不在 worker 自身配置内

本要求适用于**平台托管(platform-managed)**部署模式:此模式下 worker 自身配置 SHALL 只含部署级静态连接信息(队列/底座/embedder/Vault 接入);connector 配置(源地址/参数/凭据)SHALL NOT 出现在 worker 自身配置文件中——它由 Platform 注册表 + Vault 持有,随 job 下发。**standalone 部署模式**(见 `kb-standalone-ingest`)是另一形态:KB 服务从自己的 `kb-service.yaml` 持有 connector 配置、在本地解析凭据,不依赖 Platform 下发。

#### Scenario: 平台托管模式 worker 配置不含 connector

- **WHEN** 平台托管模式下检视 `kb-worker.env.example` 与 worker 配置加载
- **THEN** 不含任何具体 connector 的源地址/参数/凭据;这些经 job 下发

#### Scenario: standalone 模式连接器配置在 KB 服务

- **WHEN** standalone 模式下 KB 服务运行 ingest
- **THEN** connector 配置来自 KB 服务的 `kb-service.yaml`,凭据在 KB 主机本地按 `credential_ref` 解析
- **AND** 不依赖 Platform 注册表 / job 下发

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

### Requirement: kb-worker 消费 reindex job

kb-worker SHALL 消费 `reindex` 类型的 job,作为 KB 向量索引重建的**唯一写者**。消费时 SHALL 由 job 的 `tenant_id`/`kb_id` 构造重建请求,经 **`vector_store` 公共 reindex API**(非内部实现)从该 KB 在 `kb.db` 的存量 chunk 重建其向量命名空间;重建所用命名空间 SHALL 与 ingest 写入该 KB 向量时的命名空间**一致**(否则重建到错误命名空间、检索读不到)。reindex job 的入队方为 `fleetent kb reindex`(见 kb-standalone-ingest);单 reindex 失败 SHALL 记录到 job 终态,不影响其它 job。

#### Scenario: worker 执行 reindex job
- **WHEN** 队列有 pending `reindex` job 且 `fleetent kb worker` 在跑
- **THEN** worker 认领并经 `vector_store` 公共 reindex API 重建该 KB 的向量命名空间(从存量 chunk re-embed)
- **AND** 重建后该 KB 检索命中与重建前一致(命名空间对齐)

#### Scenario: reindex 失败落终态
- **WHEN** 某 `reindex` job 执行中失败
- **THEN** 该 job 记为 failed(带错误摘要),不阻塞后续 job,不破坏既有向量库可读性

### Requirement: 多租户 worker per-tenant secret 隔离

多租户 kb-worker 解析 connector 凭证(`credential_ref` 的 `env:` 引用)时 SHALL 对**该 job 所属租户的 scoped env**(从该租户 `tenants/<tenant>/kb/.env` 载为局部映射)解析,SHALL NOT 经进程全局 `os.environ` 累加解析。per-tenant `.env` 的加载 SHALL NOT 污染进程全局环境(不 `load_dotenv` 进 `os.environ`)。因此**不同租户即便使用同名 env 变量,各 connector SHALL 解析出各自租户的凭证**,不发生跨租户串号/数据泄漏。standalone / 单租户(`--tenant` 锁 或 `agent run` 同机)路径 MAY 沿用进程 `os.environ` 解析(向后兼容)。

#### Scenario: 同名 env 变量跨租户不串
- **WHEN** 租户 A 与 B 的 connectors 都引用同名 env 变量(如 `FLEETENT_GOOGLE_DRIVE_ACCESS_TOKEN`)但各自 `.env` 值不同,worker 先后处理 A、B 的 connector_sync
- **THEN** A 的同步用 A 的凭证、B 的同步用 B 的凭证(各自租户 scoped env 解析)
- **AND** 处理 B 时不因进程全局 env 已被 A 设值而误用 A 的凭证

#### Scenario: per-tenant .env 不污染全局
- **WHEN** worker 加载某租户 `.env` 以解析其 connector 凭证
- **THEN** 该加载产出局部 env 映射供本 job 解析,不写入进程全局 `os.environ`
- **AND** 后续其它租户 job 的解析不受此前租户 env 残留影响

