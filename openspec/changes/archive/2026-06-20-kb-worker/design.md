## Context

`kb-ingest-queue` 落地后,触发只入队,消费是临时内联 drain。本 change 用 `fleetent kb worker` 作唯一消费者替换它。ingest 核 `knowledge_base.ingest` 已是干净组件(护栏不 import platform);worker 是它的异步调用壳。

## Goals / Non-Goals

**Goals:** `fleetent kb worker` 单一消费者进程;移除过渡 drain;admin sync 改入队+轮询;单一写入方。

**Non-Goals:** 不做 worker 配置文件(后续 `kb-worker-config-file`,本 change 用 env/默认);不做凭据 ref 运行时解析(后续 `connector-cred-job-ref`);不做分布式部署编排(worker 进程怎么被 supervise 是部署事,单机作 platform 旁兄弟进程即可)。

## Decisions

### D1:worker 是 `fleetent` 子命令,懒加载,经 db.py 读队列

`fleetent kb worker`(对齐 `node start`/`chat` 的子命令模式):`__main__.py` 加 `kb-worker` 分支懒加载。worker 循环:claim(原子)→ 调 `knowledge_base.ingest` 核 → mark done/failed(retry)。worker 经 `db.py` 边界访问 `kb_ingest_jobs`,**不 import platform**(护栏强制)。

### D2:唯一消费者 / 单一写入方

设计上单 worker;但 claim 用原子 UPDATE(防重启/竞态重复领取)。KB 写入只发生在 worker 调核的路径——单一写入方,保证串行/可重试/隔离(这是队列+worker 的核心价值)。

### D3:移除过渡 drain,admin sync 改入队+轮询

删掉 `kb-ingest-queue` 的临时内联 drain。admin sync 端点:入队 → 轮询 job 状态直至 done/failed → 返回结果(同步体验、worker 异步执行)。生产**无任何绕过队列/worker 的 ingest 路径**;直接调核仅在测试(in-process)。

### D4:单机也起 worker(消模式)

单机:worker 作 platform 旁的兄弟进程(部署起两个进程)。分布式:独立 worker host。机制一致,只差 co-location——不为单机做"内联特例"(那又是两套消费路径)。

## Risks / Trade-offs

- **[过渡 drain 必须删干净]** 残留会变成第二条消费路径。tasks 显式核 `git grep` 无残留内联 drain。
- **[admin sync 轮询超时]** 大 KB ingest 慢;admin sync 轮询需有超时/返回 job id 让调用方后续查,不无限阻塞。design 取"超时后返回 job id + 当前状态"。
- **[单机多一个进程]** 接受(平台始终在场 + worker 廉价空转轮询);uniformity > 进程数。
