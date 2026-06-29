## Context

extraction(`run_entity_extraction`)当前只经 admin/CLI 显式触发,ingest 不抽取 → 图谱默认空。Tier-1 已落地:`fix-kb-ingest-lifecycle`(re-ingest overwrite = delete-then-insert,delete 级联清实体)、`kb-ingest-worker-reliability`(worker 存活可观测)。本 change 复用该队列/worker,把"填图谱"接到 ingest 事件上,按 KB opt-in。配套的"查图谱"是独立的 `kb-retrieval-planner-default`(E1)。

## Goals / Non-Goals

**Goals:**
- KB 级 opt-in:开启的 KB 在 ingest 后 per-document 异步入队 extraction,worker 执行,非阻塞、失败优雅降级。
- re-ingest 覆盖时为新版本重新入队。
- 抽取模型经 HTTP route,on-prem 默认自托管。

**Non-Goals:**
- 不改 graph_search / planner / search() 行为(查图是 E1)。
- 不加周期性 scheduler 主动扫描抽取(事件驱动,非定时)。
- 不改显式 extraction run、extraction schema、deterministic extractor。
- 默认(未开启 KB)行为完全不变。

## Decisions

### 决策:per-document 异步入队,复用 kb_ingest_jobs + worker
- ingest 写完 document 后,若该 KB 开启,worker(或 ingest 完成回调)经既有入队 seam 写一条 `extraction` job(payload 含 tenant/kb/document_id)。worker 认 `extraction` job_type 调 `run_entity_extraction`。
- **为什么**:复用 Tier-1 加固的单消费者队列,保持"单一写入方"与 worker ✗→platform 解耦;事件驱动避免周期 scheduler。
- **替代**:ingest 同步抽取。否决——抽取走 LLM,慢且会阻塞导入。

### 决策:opt-in 开关放 KB 定义(per-tenant kb.db 的 `knowledge_bases.extraction_enabled`)
- worker 读 kb.db(经 db.py)即可判定,无需 import platform,保解耦。默认 0(关)。
- **迁移**:`core/migrations.py` 嵌入式 forward-only 加一条(ALTER TABLE 加列 + 默认 0),版本号取当前 MIGRATIONS 末尾下一个整数,**勿硬编码**(避免与其它 kb.db 迁移撞号)。非 Alembic。
- **替代**:放 platform 配置 / 随 job payload 下发。否决——worker 读 kb.db 最直接且不破解耦。

### 决策:失败非阻塞,图谱缺失即降级
- extraction job 失败(达 retry 上限)→ 文档 chunks 仍可检索,只是图谱缺该文档实体。E1 的 graph 检索对缺失数据天然返回更少结果,hybrid 仍兜底。

### 决策:抽取模型 = model policy `kb_extraction` task 的 HTTP route,on-prem 默认自托管
- 与 embedding 姿态对称:route 按部署配置,默认指向可自托管模型;云 API 仅在部署明确接受 KB 内容外发时 opt-in。**不硬编码云默认**(数据主权铁律)。

## Risks / Trade-offs

- **[抽取成本/延迟堆积]** 大批 ingest → 大量 extraction job 排队烧 LLM。**Mitigation**:per-KB opt-in(默认关,谁要图谱谁开);worker 串行 drain 天然限流;失败非阻塞不拖垮 ingest。
- **[re-ingest 竞态]** 覆盖删旧+插新与旧 extraction job 并发。**Mitigation**:extraction job 按 document_id 执行,覆盖已先删旧 document(含旧实体,fix-lifecycle 级联);新 job 针对新 document_id 重新抽取;worker 单消费者顺序处理降低竞态。
- **[嵌入式迁移撞号]** 并行 change 同改 kb.db schema。**Mitigation**:wave 2 内只有本 change 动 kb.db schema(E1 不动);版本号取末尾下一个整数、勿硬编码;apply 收尾跑 kb.db 迁移相关测试见绿。
- **[数据主权误配]** 部署误把 route 指向云。**Mitigation**:spec 与 design 明确 on-prem 默认自托管;文档强调云为显式 opt-in。

## Migration Plan

- 嵌入式 forward-only 加 `knowledge_bases.extraction_enabled`(默认 0)→ 存量 KB 默认关,行为不变。
- 部署:开启某 KB 后,后续 ingest 自动填图;存量已 ingest 文档需一次显式 extraction run 回填(沿用既有 admin/CLI),本 change 不做一次性回填。
- 回滚:还原代码 + 列可保留(默认 0 不影响)。

## Open Questions

- per-document job vs per-ingest-batch job:默认 per-document(粒度细、失败隔离好);若大文档批量 ingest 产生过多 job,实现期可评估批量入队,不阻塞 propose。
