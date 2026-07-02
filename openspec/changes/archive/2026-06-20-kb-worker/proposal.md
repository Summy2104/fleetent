## Why

`kb-ingest-queue` 把所有 ingest 触发改成了入队,但消费端目前是"过渡内联 drain"。本 change 引入 **`fleetent kb worker`**——队列的**唯一消费者、KB 的唯一写入方**,异步 drain 队列 → 调 `knowledge_base.ingest` 核 → 写 KB。这把重活/崩溃从控制面隔离出去,并实现 target-architecture §12 的"唯一 worker、单一写入方"不变量。**单机也拆 worker**(为消模式/隔离,非扩容):单机作 platform 旁兄弟进程,分布式作独立 worker host——机制一致,只差 co-location。

**前置**:`kb-ingest-queue` 已落地。

## What Changes

- **新增 `fleetent kb worker` 子命令**:长驻进程,轮询 claim 队列 → 调 ingest 核 → mark done/failed;唯一消费者(claim 原子,单一写入方)。
- **移除过渡内联 drain**:`kb-ingest-queue` 里临时的同进程 drain 删除,改由 worker 统一消费。
- **admin sync = 入队 + 轮询 job 状态**:不再同进程 drain,而是入队后查 job 状态直至完成(同步体验、worker 异步执行)。
- **直接调 ingest 核仅限测试**:生产无任何绕过队列/worker 的 ingest 路径。

## Capabilities

### New Capabilities
- `kb-ingest-worker`:`fleetent kb worker` 单一消费者进程(drain 队列、调核、单一写入方、retry)。

### Modified Capabilities
- `agent-runtime-cli`:新增 `fleetent kb worker` 子命令(懒加载,不在 `fleetent agent run` 启动路径触发)。
- `kb-ingest-queue`:消费端由过渡内联 drain 改为 `kb-worker` 唯一消费;移除过渡 drain。

## Impact

**owning package**:`knowledge_base/ingest`(worker 入口/消费循环)+ `src/fleetent/__main__.py`(`kb-worker` 子命令分发)

**public API surface**:新增 `fleetent kb worker` 子命令;admin sync 端点改为入队+轮询状态

**owned tables**:无(复用 `kb_ingest_jobs`)　**config namespace**:worker 连接配置见后续 `kb-worker-config-file`(本 change 先用环境变量/默认)　**migration**:无

**cross-module dependencies**:worker 经 `db.py` 边界读队列、调 `knowledge_base.ingest` 核;**MUST NOT `import fleetent.platform.*`**(护栏)。worker 经 subprocess/进程独立运行,崩溃不波及控制面。

**与后续 change**:`kb-worker-config-file`(worker 配置文件化)依赖本 change;`connector-cred-job-ref`(运行时按 ref 解析凭据)在 worker 消费路径上接入。
