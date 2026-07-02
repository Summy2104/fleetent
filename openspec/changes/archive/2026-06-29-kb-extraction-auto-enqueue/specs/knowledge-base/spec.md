## MODIFIED Requirements

### Requirement: Explicit entity extraction runs
knowledge-base SHALL 支持显式 extraction run;此外 SHALL 支持**按 KB opt-in 的 ingest 后自动入队 extraction**。默认(未开启的 KB)SHALL NOT 自动抽取,ingest/sync 不产生 extraction 副作用;仅当某 KB 的 `extraction_enabled` 为真时,ingest 后自动入队 per-document extraction。

#### Scenario: Document extraction run
- **WHEN** 调用方显式对一个 document 运行 extraction
- **THEN** 系统只扫描该 document 的 chunks
- **AND** 写入 extraction run summary、entities、mentions 和 relations

#### Scenario: Knowledge-base extraction run
- **WHEN** 调用方显式对一个 KB 运行 extraction
- **THEN** 系统逐 document 扫描该 KB 的 chunks
- **AND** 单 document 失败不阻止后续 document
- **AND** run summary 记录 failed count

#### Scenario: Ingest does not auto-extract by default
- **WHEN** KB ingest 或 connector sync 写入 document / chunks 且该 KB 未开启 `extraction_enabled`
- **THEN** 系统不运行 entity extraction

#### Scenario: Opt-in KB auto-enqueues extraction after ingest
- **WHEN** KB ingest 写入 document / chunks 且该 KB `extraction_enabled` 为真
- **THEN** 系统在 ingest 完成后异步入队该 document 的 extraction job,不阻塞 ingest

### Requirement: Entity extraction exclusions
knowledge-base entity extraction SHALL NOT implement graph search、periodic scheduler auto-discovery、entity merge review 或 document ACL。opt-in 的 ingest 后自动入队 extraction 经既有 `kb_ingest_jobs` 队列与 `fleetent kb worker` 异步执行(事件驱动,非周期 scheduler),不属于本排除项。

#### Scenario: Graph search remains out of scope
- **WHEN** entity extraction change 完成
- **THEN** `search()` 和 hybrid ranking 不因 entities / relations 改变
- **AND** 不新增 graph traversal search

#### Scenario: Periodic scheduler remains out of scope
- **WHEN** entity extraction change 完成
- **THEN** 不新增周期性 scheduler 去主动发现并抽取文档
- **AND** 自动抽取仅由"opt-in KB 的 ingest 事件"驱动,经既有 ingest worker 执行,而非定时轮询

## ADDED Requirements

### Requirement: Auto-enqueue entity extraction after ingest
当 KB 的 `extraction_enabled` 为真时,knowledge-base SHALL 在 ingest 写入 document 后,经既有 `kb_ingest_jobs` 入队 seam 异步入队一个 per-document `extraction` job,由 `fleetent kb worker` 消费执行;入队与执行 SHALL NOT 阻塞 ingest,且单 extraction 失败 SHALL NOT 影响该文档的可检索性。抽取所用模型经 model policy 的 `kb_extraction` task 以 HTTP route 访问,route 由部署配置,on-prem 默认 SHALL 可自托管,不硬编码云默认。

#### Scenario: Worker runs enqueued extraction
- **WHEN** 存在 `extraction` job 且 `fleetent kb worker` 在跑
- **THEN** worker claim 该 job、对目标 document 运行 `run_entity_extraction`、写 entities/mentions/relations、置 job done

#### Scenario: Extraction failure is non-blocking
- **WHEN** 某 document 的 extraction job 失败(达 retry 上限)
- **THEN** 该 document 的 chunks 仍可被 search 检索
- **AND** 图谱只是缺该 document 的实体证据,系统不报致命错误

#### Scenario: Re-ingest re-enqueues extraction
- **WHEN** 以相同身份 re-ingest 覆盖一个 document 且该 KB 开启 `extraction_enabled`
- **THEN** 系统在删旧 document(连带清旧实体证据)、插新 document 后,为新版本重新入队 extraction

#### Scenario: Default KB does not enqueue
- **WHEN** 未开启 `extraction_enabled` 的 KB 完成 ingest
- **THEN** 系统不入队任何 extraction job
