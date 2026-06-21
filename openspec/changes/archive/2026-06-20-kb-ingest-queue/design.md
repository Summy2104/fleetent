## Context

KB ingest 现状:`kb_admin_api` 同步 `asyncio.run(sync_local_directory(...))` 在 platform 进程内跑——阻塞控制面、无重试、无串行。目标(target-architecture §12):多触发器 → 一个 DB 队列 → 唯一 worker → ingest 核。本 change 做队列 + 入队 + 触发器改造;worker 是后续 change。

## Goals / Non-Goals

**Goals:** 持久 DB 背队列;所有触发器改为入队;claim/done/retry 语义;不阻塞控制面。

**Non-Goals:** 不实现 `kb-worker` 进程(后续);不改 ingest 核逻辑;不做凭据 ref 运行时解析(后续 `connector-cred-job-ref`,本 change 只预留 `cred_ref` 字段);不碰底座可插拔。

## Decisions

### D1:队列落管理库(Alembic),与 scheduled_tasks 同属编排状态

`kb_ingest_jobs` 放管理库——precedent 是 `scheduled_tasks`(同为编排/调度状态)。platform 入队(自然)。**worker(后续)经 `db.py` 统一边界读/claim 队列,不 `import fleetent.platform.*`**——DB 访问不是代码 import,boundary 护栏不破。
> 备选:专用 ingest 队列 store(platform/worker 都连、谁都不"拥有")。更"干净"但多一个库;管理库方案更简单且有先例。倾向管理库,apply 时若 worker-读-管理库被判越界再升级为专用 store。

### D2:入队即解析非密配置 + 凭据 ref(不写明文)

入队时 platform 读 connector 注册表,把**非密 connector 配置**(源地址/参数)+ **`cred_ref`**(Vault 引用)写进 job。**明文凭据不进队列**(at-rest 安全)。运行时按 ref 解析是后续 `connector-cred-job-ref` 的事;本 change 只保证字段就位、入队不落明文。

### D3:claim 原子性(单消费者)

claim = 单条 `UPDATE ... SET status='claimed', claimed_at=... WHERE id=(SELECT ... WHERE status='pending' ORDER BY created_at LIMIT 1) RETURNING ...`(或等价的 SQLite 原子取一)。保证多消费者并发时不重复领取(虽然目标是单 worker,claim 仍要原子以防重启/竞态)。done/failed 更新 status;failed 且 attempts<上限则回 pending 重试。

### D4:过渡消费(worker 落地前不回退功能)

`kb-worker` 未落地前,提供最小过渡:admin sync / 文档导入 / connector execute sync 入队后**同进程内联 drain 这一条 job 并等完成**(保持功能不回退)。当前代码树中没有现成的 KB cron/webhook 执行入口；后续若新增,复用同一 drain seam,待 `kb-worker` 落地后统一移除过渡 drain。

## Risks / Trade-offs

- **[worker 读管理库的边界]** D1 备选已说明;apply 时核 `test_module_dependency_guardrails`,worker 只经 db.py、不 import platform。
- **[过渡期双路径]** worker 落地前的内联 drain 是临时;`kb-worker` change 必须移除它,避免长期两套消费。tasks 标注。
- **[迁移撞号]** `kb_ingest_jobs` 迁移版本号 apply 时取 head 续号,勿硬编码。
