# kb-standalone-ingest Specification

## Purpose
定义 standalone KB 服务在无 platform 环境下的配置、本地队列与手动 ingest 契约。
## Requirements
### Requirement: Standalone KB service config contract

KB 服务 SHALL 以**两层 config**驱动,默认**单机多租户**:

- **本机服务级 config** `$FLEETENT_HOME/kb-service.yaml`(一份,kb-serve 与 kb-worker 都读):`service`(host/port/**共享 service_key_ref**)、`retrieval`(default_mode/rerank/top_k)、`embedding`(endpoint/model/dimensions,**全机一个模型**)、`extraction`(enabled/endpoint/model)、`chunking`(chunk_size/chunk_overlap)。
- **per-tenant config** `$FLEETENT_HOME/tenants/<tenant_id>/kb/connectors.yaml` + 同目录 `.env`(secret):只含该租户 `connectors`(各源 type/kb_id/scope/`sync_interval_seconds`/`credential_ref`)。
- **租户发现**:服务扫 `$FLEETENT_HOME/tenants/*/kb/data/`(有 `kb.db` 者即在册,动态,新租户 kb home 一建即纳入)。

仓库 SHALL 提供根模板 `kb-service.yaml.example`(本机服务级)与 `kb-service.env.example`;系统 SHALL 提供 `fleetent kb init-config`,生成本机 `kb-service.yaml` 及为已存在租户 scaffold `tenants/<tenant_id>/kb/connectors.yaml` + `.env`。embedding SHALL 全机一个模型:与 per-KB embedding 身份校验相容(所有 KB 同模型);换本机 embedding 模型 SHALL 需 `kb reindex` 重建各 KB 向量。服务 MAY 经 `--tenant <id>` 锁单租户。

#### Scenario: 本机 config 驱动多租户服务
- **WHEN** `fleetent kb serve` / `fleetent kb worker` 以本机 `$FLEETENT_HOME/kb-service.yaml` 启动(默认不锁租户)
- **THEN** 二者读同一本机服务级 config;服务本机所有在册租户,按 principal / job 的 tenant_id 路由到各租户 `tenants/<t>/kb/data/`

#### Scenario: per-tenant 只剩 connectors
- **WHEN** 查看某租户 kb home
- **THEN** `tenants/<t>/kb/connectors.yaml` 只含该租户连接器定义,secret 在同目录 `.env`;service/embedding/rerank 等不再 per-tenant(在本机 config)

#### Scenario: 提供 example 与 init-config
- **WHEN** 运行 `fleetent kb init-config`
- **THEN** 生成本机 `kb-service.yaml`(从根 example),并为已存在租户 scaffold `tenants/<t>/kb/connectors.yaml` + `.env`

### Requirement: Local credential resolution

standalone KB 服务的连接器凭据 SHALL 在 **KB 主机本地**经 `credential_ref`(`env:NAME` / `file://PATH`)解析,真值 SHALL NOT 经网络下发。多个连接器 SHALL 可共用同一 `credential_ref`(指向同一 env)。

#### Scenario: 本地解析凭据
- **WHEN** worker 执行某连接器同步
- **THEN** 经其 `credential_ref` 在本地 env/file 解析真实凭据
- **AND** 真实凭据未经任何网络下发到本进程

#### Scenario: 连接器共用凭据
- **WHEN** 两个连接器的 `credential_ref` 指向同一 env 名
- **THEN** 二者共用该凭据,`.env` 只需一条

### Requirement: KB-local ingest queue, worker and sweep

standalone 模式下 ingest 队列 / worker / sweep SHALL 全在 KB 主机本地(非 management.db)。kb-worker 默认**单机多租户**:SHALL **轮询本机所有在册租户的 per-tenant 队列** `tenants/<t>/kb/data/kb_ingest_queue.db`,认领 job 后按 job 的 tenant_id 经 `TenantRouter` 写该租户 `kb/data/`,并**按需加载该租户** `tenants/<t>/kb/connectors.yaml` + `.env`(connector_sync 才需 secret);sweep 由 kb-worker 在循环中按各租户 connector 的 `sync_interval_seconds` 到期入队(不依赖 kb-serve、不依赖 platform)。worker MAY 经 `--tenant <id>` 只 drain 该租户队列。**单写者纪律不变**:各租户 KB 的内容/向量写仍唯一经 kb-worker。每租户数据 SHALL 物理隔离(独立 `tenants/<t>/kb/data/` SQLite),多租户共享的是进程而非数据。

#### Scenario: 多租户轮询与写
- **WHEN** kb-worker 默认启动,`tenants/A/` 与 `tenants/B/` 各有 pending job
- **THEN** worker 轮询两租户队列、分别认领,按 job.tenant_id 写各自 `tenants/<t>/kb/data/`,互不串写
- **AND** 处理 A 的 connector_sync 时加载 `tenants/A/kb/.env`,不加载 B 的 secret

#### Scenario: 新租户动态纳入
- **WHEN** 运行中新建租户 kb home(`tenants/C/kb/data/kb.db` 出现)
- **THEN** kb-worker 下一轮轮询即纳入租户 C,无需重启

#### Scenario: --tenant 锁单租户
- **WHEN** kb-worker 以 `--tenant A` 启动
- **THEN** 只 drain `tenants/A/kb/data/kb_ingest_queue.db`,不碰其它租户

### Requirement: Boot validation of config and credentials

KB 服务启动 SHALL 校验配置完整性:所有连接器引用的凭据 env/file SHALL 存在——既包括 `credential_ref`,也包括连接器实际声明的**颗粒凭据字段**(`access_token_env` / `refresh_token_env` / `client_id_env` / `client_secret_env` / `token_uri_env` / `username_env` / `api_token_env` 等);以及 embedding / extraction 配置的 `api_key_env`(若设置)、rerank 配置的 `api_key_env`(若启用且设置)所指向的 env/file SHALL 存在;embedding endpoint SHALL 配置。任一缺失 SHALL 启动即失败并指出缺项(不延迟到运行时才炸)。

#### Scenario: 缺凭据启动失败
- **WHEN** 某连接器的 `credential_ref` **或其声明的任一颗粒 `*_env`**,或 embedding / extraction / 启用的 rerank 的 `api_key_env` 所指 env/file 不存在
- **THEN** 服务启动失败并报出缺失的引用

#### Scenario: 颗粒 *_env 缺失被 boot 捕获
- **WHEN** 连接器用颗粒 `*_env`(如 `access_token_env`)而非 `credential_ref`,且该 env 未设置
- **THEN** 启动即失败(不延迟到运行时 sync 才报错)

#### Scenario: 配置齐全启动成功
- **WHEN** 所有引用就位、embedding 已配
- **THEN** 服务正常启动

### Requirement: Platform-optional operation

standalone KB 服务的 ingest 与检索 SHALL 能在**无 platform、management.db 不存在**的环境下完成;管理(改连接器/绑定)在该环境下不可用,但已配置的 ingest/检索 SHALL 继续运作。

#### Scenario: 无 platform 完成 ingest 与检索
- **WHEN** 环境无 platform、无 management.db,KB 服务按 `kb-service.yaml` 启动
- **THEN** connector sync / ingest / 检索均可完成
- **AND** 进程不因 management.db 缺失而失败

### Requirement: 手动本地 ingest 命令

KB 服务 SHALL 提供一个**命令式本地 ingest 入口** `fleetent kb ingest`,把本地目录或单文件推进指定 KB,**纯 KB 服务侧、不依赖 platform**。该命令 SHALL 复用 `--config <kb-service.yaml>` 解析 tenant_id、队列路径与 embedding 配置(与 `kb-worker`/`kb-serve` 同源)。

ingest SHALL 经**入队**完成:命令把 `sync_directory` job 入本租户本地队列(`kb_ingest_queue.db`),由运行中的 kb-worker 作为**唯一消费者**抽取执行(切块 → 向量化 → 写本租户 `kb/data/kb.db`);命令 SHALL NOT 在自身进程内直写 `kb.db`(守单写者纪律)。入队前 SHALL 校验目标 KB 存在,不存在则报清晰错误(指引经平台创建 KB)。ingest SHALL 幂等(再次对同一路径运行按内容指纹增量)。

`<path>` SHALL 支持目录(递归)与单文件;支持格式与 `LocalDirectoryDataSource` 一致(txt/md/html/pdf/docx/pptx/xlsx)。

#### Scenario: CLI 把本地目录灌进 KB
- **WHEN** 运维运行 `fleetent kb ingest --config <kb-service.yaml> --kb <kb_id> <dir>`
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

`kb-service.yaml.example` 提供的样例连接器 SHALL 默认 `enabled: false`,使 ``kb-service` `init-config`` scaffold 出的配置在未填真实凭据时 `kb-worker` 启动后**不会**立即尝试外部同步并运行时失败。

#### Scenario: 开箱不触发失败同步
- **WHEN** 运维以未修改的 scaffolded 配置启动 `kb-worker`
- **THEN** sweep 不对占位凭据的样例连接器入队同步 job
- **AND** 无运行时连接失败噪声

### Requirement: Standalone rerank 配置

`kb-service.yaml` MAY 含 `rerank` 段(`backend` / `endpoint` / `model` / `api_key_env`);当 `backend` 非 `disabled` 时,KB 服务进程 SHALL 据此配置 rerank provider,使检索在请求 rerank 时(见 `kb-read-service` 透传)真正经该 provider 重排。默认 `backend: disabled`(未配 rerank 服务时不影响启动与检索)。仓库 example SHALL 预置该段但默认禁用,endpoint 指向自托管 rerank 服务(如 Infinity)的约定地址,运维填端点并启用即生效。

#### Scenario: rerank 默认禁用不影响运行
- **WHEN** `kb-service.yaml` 未配 rerank 或 `backend: disabled`
- **THEN** 服务正常启动与检索,检索不重排(与扩展前一致)

#### Scenario: 启用 rerank 后真重排
- **WHEN** `rerank.backend: http` + 有效 endpoint,且检索请求带 `rerank=true`
- **THEN** 进程的 rerank provider 经该 endpoint 对候选重排

### Requirement: 手动 extraction 命令

KB 服务 SHALL 提供命令式 extraction 入口 `fleetent kb extract`,对指定 KB **开启实体/关系抽取并回填存量文档**,**纯 KB 服务侧、不依赖 platform**。命令 SHALL 复用 `--config <kb-service.yaml>` 解析 tenant_id/队列/抽取模型配置。

- 命令 SHALL 置该 KB `extraction_enabled=true`(对存量 KB 亦可开启)。
- 回填 SHALL 经**入队**完成:遍历该 KB 存量文档,每文档入队一个 `extraction` job(与 ingest 侧 auto-enqueue 同形),由 kb-worker 作为**唯一消费者**抽取执行并写 `kb_entities`/`kb_entity_mentions`/`kb_relations`;命令 SHALL NOT 在自身进程内直写 kb.db。
- 入队前 SHALL 校验目标 KB 存在。`--wait` 时 SHALL 阻塞至完成并打印 documents/entities/relations 计数,超时提示检查 kb-worker。
- 抽取模型 SHALL 取自 `kb-service.yaml` 的 `extraction` 段(`kb_extraction` route);仓库 example SHALL 预置该段(默认 `enabled: false`,endpoint 指向自托管抽取模型),运维填模型并开启即用。

#### Scenario: 开启并回填存量文档
- **WHEN** 运维运行 `fleetent kb extract --config <kb-service.yaml> --kb <kb_id>`
- **THEN** 该 KB `extraction_enabled` 置真,其存量文档各入队一个 `extraction` job
- **AND** kb-worker 抽取执行,写 `kb_entities`/`kb_entity_mentions`/`kb_relations`,全程不依赖 platform

#### Scenario: 目标 KB 不存在
- **WHEN** `--kb` 指向本租户 kb.db 不存在的 KB
- **THEN** 命令报清晰错误、不入队

#### Scenario: 抽取模型未配则明确失败
- **WHEN** `extraction` 段未配 endpoint/model 而尝试抽取
- **THEN** 以清晰错误提示配置抽取模型(不静默产出空图)

### Requirement: extraction 填充图后 planner 检索端到端命中

extraction 填充实体/关系图后,agent 检索在 `use_planner=true`(经 `kb-read-service` 透传,见 `kb-http-quality-passthrough`)时 SHALL 能经 `plan_knowledge_search` + graph_search 命中实体/关系关联的 chunk。extraction SHALL 保持 per-KB opt-in(默认关),graph 检索 SHALL 保持 planner 触发(不新增默认检索开销)。

#### Scenario: 抽取后图检索命中
- **WHEN** 某 KB 已开 extraction 并抽取完成、检索请求 `use_planner=true` 且 query 命中实体/关系
- **THEN** planner 经 graph_search 返回实体/关系关联的 chunk

### Requirement: 手动建库命令

KB 服务 SHALL 提供命令式建库入口 `fleetent kb create`,在指定租户创建一个知识库,**纯 KB 服务侧、不依赖 platform**。命令 SHALL 复用 `--config <kb-service.yaml>` 解析 tenant_id 与 data_dir(与 `kb serve`/`kb worker`/`kb ingest` 同源),并调知识库管理公共 API 在本租户 `kb.db` 建库。建库 SHALL 幂等:目标 KB 已存在时以成功 no-op 返回(打印现状),不报错、不重复创建。

- 命令签名 SHALL 为 `fleetent kb create --config <kb-service.yaml> --kb <kb_id> [--description <text>]`。
- 全程 SHALL NOT 读写 management.db、SHALL NOT 依赖 platform 或 admin API。

#### Scenario: standalone 建库
- **WHEN** 运维运行 `fleetent kb create --config <kb-service.yaml> --kb <kb_id>`
- **THEN** 本租户 `kb.db` 出现该 KB,后续 `kb ingest`/`kb extract`/检索可用
- **AND** 全程不依赖 platform 或 management.db

#### Scenario: 重复建库幂等
- **WHEN** 对已存在的 KB 再次运行 `kb create`
- **THEN** 命令以成功返回(no-op),不报错、不产生重复记录

### Requirement: 手动重建索引命令

KB 服务 SHALL 提供命令式向量重建入口 `fleetent kb reindex`,对指定 KB 从 `kb.db` 存量 chunk 重建其向量索引(`kb_vectors.db`),**纯 KB 服务侧、不依赖 platform**。重建 SHALL 经**入队**完成:命令把一个 `reindex` job 入本租户 `kb_ingest_queue.db`,由运行中的 kb-worker 作为**唯一写者**执行重建(经 `vector_store` 公共 reindex API);命令 SHALL NOT 在自身进程内直写 `kb_vectors.db`(守单写者纪律,与 `kb ingest`/`kb extract` 同形)。入队前 SHALL 校验目标 KB 存在。`--wait` 时 SHALL 阻塞至 job 终态并打印重建计数,超时提示检查 kb-worker。

#### Scenario: 入队重建并由 worker 执行
- **WHEN** 运维运行 `fleetent kb reindex --config <kb-service.yaml> --kb <kb_id>`
- **THEN** 一个 `reindex` job 入本租户 `kb_ingest_queue.db`
- **AND** 运行中的 kb-worker 消费它,按该 KB 的向量命名空间从存量 chunk 重建 `kb_vectors.db`,全程不依赖 platform

#### Scenario: 目标 KB 不存在
- **WHEN** `--kb` 指向本租户 `kb.db` 不存在的 KB
- **THEN** 命令报清晰错误、不入队

#### Scenario: --wait 回报结果
- **WHEN** 运维加 `--wait`
- **THEN** 命令阻塞至该 reindex job 终态并打印重建计数(如 namespace/重建条数)
- **AND** 若超时未被消费,提示检查 kb-worker 是否在运行

