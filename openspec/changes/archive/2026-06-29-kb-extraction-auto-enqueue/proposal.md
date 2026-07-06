## Why

实体抽取(extraction)当前**只能显式触发**(admin / CLI),ingest 不自动抽取——结果是图谱(`kb_entities` / `kb_entity_mentions` / `kb_relations`)默认**长期为空**,graph 检索能力无数据可用。我们已决定走 A+(被动注入 + 激活图谱):要让图谱真正可用,需要在导入文档后**自动、按 KB 选择性地**填充图谱,且不能阻塞 ingest、不能违反数据主权。

## What Changes

- **ingest 后按 KB opt-in 自动入队 extraction**:KB 级新增 `extraction_enabled` 开关(默认关)。当某 KB 开启时,ingest 写入 document/chunks 后 SHALL **异步入队**一个 per-document extraction job(复用既有 `kb_ingest_jobs` 队列 + `fleetent kb worker`,新增 `extraction` job_type),**不阻塞** ingest 完成。
- **worker 消费 extraction job**:worker SHALL 认 `extraction` job_type,运行 `run_entity_extraction` 写 entities/mentions/relations;单 job 失败非阻塞(图谱缺该文档证据,检索优雅降级),按既有 retry 上限重试。
- **re-ingest 重新入队**:同身份覆盖(已落地的 overwrite)删旧 document 时连带清旧实体(已落地的 delete 级联),插新 document 后 SHALL 为新版本重新入队 extraction(KB 开启时)。
- **抽取模型经 HTTP route**:extraction 走 model_router 的 `kb_extraction` task(HTTP),route 按部署配置;**on-prem 默认必须可自托管,不硬编码云默认**;云 API 仅为"该部署明确接受其 KB 内容外发"时的 opt-in(数据主权约束,与 embedding 姿态对称)。

不改变:显式 extraction run(admin/CLI)继续可用;默认(未开启的 KB)行为不变、ingest 仍不抽取;extraction schema / deterministic extractor / `run_entity_extraction` 语义;graph_search / planner 行为(本 change 只填图,不改检索——查图是 E1)。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `knowledge-base`: 放开"ingest 不自动抽取"为"按 KB opt-in 自动入队抽取";修订"extraction 不进 worker / 只 explicit"的排除项为"opt-in 时经既有 ingest worker 异步执行";新增 ingest 后 per-document 自动入队 extraction 的行为要求。
- `kb-ingest-worker`: worker 新增 `extraction` job_type 的消费(同一 worker、同一队列,仍是唯一消费者)。

## Impact

- **owning packages**:`fleetent.knowledge_base`(ingest 后入队 + worker 消费 extraction)。入队 seam 由 worker 经 `db.py` 写 `kb_ingest_jobs`,worker ✗→ `import platform`。
- **public API surface**:`run_entity_extraction` 不变;新增 `extraction` job_type;KB 定义新增 `extraction_enabled`。
- **owned tables**:`knowledge_bases`(per-tenant kb.db)新增 `extraction_enabled` 列,走 `core/migrations.py` **嵌入式 forward-only** 迁移(版本号取下一个整数,**勿硬编码**),不碰 Alembic;`kb_ingest_jobs` 复用既有列(新增 job_type 取值,非新列)。
- **config namespace**:KB 级 `extraction_enabled`;抽取模型 route 复用 model policy 的 `kb_extraction` task,无新 namespace。
- **cross-module 依赖**:无新增;复用 Tier-1 加固的队列/worker;保持解耦(worker 不 import platform)。
- **数据主权**:抽取把内部文档内容发给 LLM route → on-prem 默认自托管,云为 opt-in。
- **测试**:integration(KB 开启 → ingest 后入 extraction job → worker 跑出实体;默认关 → 不入队;失败非阻塞;re-ingest 重新入队)。
