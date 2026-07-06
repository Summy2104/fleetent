## Why

两个 KB 运维缺口:

1. **ingest 不可观测**:connector 同步状态(`knowledge_connector_status`)与 ingest job 状态(`kb_ingest_jobs`)只落 sqlite,**没有任何运维查询面**——灌文档失败、连接器同步出错,运维只能去翻 sqlite,看不到进度/失败原因。
2. **sweep 寄生在 kb-serve**:connector 定时调度的 `_sweep_loop` 跑在 **kb-serve 读服务进程的 lifespan 里**(`serve.py:137-142`)。后果:**只起 kb-worker 不起 kb-serve,connector 就永不调度**——调度器与只读服务耦合,运维语义不清。

## What Changes

- **#1 状态只读端点**:kb-serve 加 `GET /status`(与 `/search` 同款 Bearer + principal 鉴权,绑定本租户)——返回本租户 connector 状态 + 近期 ingest job(status/result)。需补 list helper:列连接器状态(`operations`)、列近期 job(`kb_ingest_jobs`,现仅 get-by-id)。
- **#5 sweep 解耦到 kb-worker**:从 `serve.py` lifespan 摘掉 `_sweep_loop`;把 sweep 挪进 **kb-worker 的 `run()` 抽取循环**(`worker.py:308`)——按 `sync_interval_seconds` 到期入队。**kb-worker 自此既抽队列又调度;只起 kb-worker 即有调度,不依赖 kb-serve**;kb-serve 变纯读。

## 边界(与并行的 D2' `kb-boot-validate-and-rerank` 划清)

只动:`knowledge_base/serve.py`(状态端点 + 摘 sweep)、`knowledge_base/worker.py`(挂 sweep)、`knowledge_base/operations.py`(连接器状态 list helper,读)、`kb_ingest_jobs.py`(job list helper,读)、`standalone_sweep.py`(若需暴露可复用入口)。
**严禁碰**(D2' 的地盘):`service_config.py`、`kb-service.yaml.example`、`config.py`/`agent_config.py`。两包代码文件完全不相交。

## Capabilities

### Modified Capabilities
- `kb-read-service`:新增只读 `GET /status`(connector + ingest job 状态);明确 kb-serve 为纯读、不再承载 sweep。
- `kb-standalone-ingest`:connector sweep 调度由 **kb-worker** 承载(从 kb-serve 解耦);只起 kb-worker 即有调度。

## Impact

- **owning area**:`knowledge_base/serve.py`、`worker.py`、`operations.py`(读)、`kb_ingest_jobs.py`(读)、`standalone_sweep.py`。**不碰 platform、不碰 D2' 文件**。
- **public surface**:kb-serve 新增 `GET /status`(只读);sweep 触发点从 kb-serve 进程移到 kb-worker 进程(部署语义变更:调度跟随 kb-worker)。
- **owned tables / config / 迁移**:无;只读既有 `knowledge_connector_status` / `kb_ingest_jobs`。
- **行为变更**:**只起 kb-serve 不再触发 connector 调度**(调度归 kb-worker)——这是刻意的解耦;compose/dev 同时起 worker+serve 不受影响。
- **cross-module / 解耦**:不新增依赖;不碰 platform。
- **测试**:`GET /status` 返回连接器+job 状态的单测/集成测;sweep 在 kb-worker 循环按 interval 入队的单测;`make test-pr` + `make test-integration-ci` 全绿。
