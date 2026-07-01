## ADDED Requirements

### Requirement: 手动本地 ingest 命令

KB 服务 SHALL 提供一个**命令式本地 ingest 入口** `fleetent kb-ingest`,把本地目录或单文件推进指定 KB,**纯 KB 服务侧、不依赖 platform**。该命令 SHALL 复用 `--config <kb-service.yaml>` 解析 tenant_id、队列路径与 embedding 配置(与 `kb-worker`/`kb-serve` 同源)。

ingest SHALL 经**入队**完成:命令把 `sync_directory` job 入本租户本地队列(`kb_ingest_queue.db`),由运行中的 kb-worker 作为**唯一消费者**抽取执行(切块 → 向量化 → 写本租户 `kb/data/kb.db`);命令 SHALL NOT 在自身进程内直写 `kb.db`(守单写者纪律)。入队前 SHALL 校验目标 KB 存在,不存在则报清晰错误(指引经平台创建 KB)。ingest SHALL 幂等(再次对同一路径运行按内容指纹增量)。

`<path>` SHALL 支持目录(递归)与单文件;支持格式与 `LocalDirectoryDataSource` 一致(txt/md/html/pdf/docx/pptx/xlsx)。

#### Scenario: CLI 把本地目录灌进 KB
- **WHEN** 运维运行 `fleetent kb-ingest --config <kb-service.yaml> --kb <kb_id> <dir>`
- **THEN** 命令将 `sync_directory` job(payload 含该路径)入本租户 `kb_ingest_queue.db`
- **AND** 运行中的 kb-worker 抽取该 job,递归扫描目录、切块、向量化并写入本租户 `kb/data/kb.db`
- **AND** 全程不依赖 platform 或 management.db

#### Scenario: 支持单文件
- **WHEN** `<path>` 指向单个受支持文件(而非目录)
- **THEN** 仅该文件被 ingest

#### Scenario: 目标 KB 不存在
- **WHEN** `--kb` 指向的 KB 在本租户 `kb.db` 不存在
- **THEN** 命令报清晰错误并指引先创建 KB,不入队无效 job

#### Scenario: --wait 回报结果
- **WHEN** 运维加 `--wait`
- **THEN** 命令阻塞至该 job 终态并打印 `scanned/ingested/skipped/failed` 计数
- **AND** 若超时仍未被消费,提示检查 kb-worker 是否在运行

### Requirement: 样例连接器默认禁用

`kb-service.yaml.example` 提供的样例连接器 SHALL 默认 `enabled: false`,使 `kb-service init-config` scaffold 出的配置在未填真实凭据时 `kb-worker` 启动后**不会**立即尝试外部同步并运行时失败。

#### Scenario: 开箱不触发失败同步
- **WHEN** 运维以未修改的 scaffolded 配置启动 `kb-worker`
- **THEN** sweep 不对占位凭据的样例连接器入队同步 job
- **AND** 无运行时连接失败噪声
