# kb-ingest-fail-closed

## Why

2026-07-06 dogfooding 逮出（bug #4）：embedding 服务不可用时，上传/同步的文档**看起来导入成功**（job=done、无错误、文档带 chunk 数出现在列表），实为"chunk 在库、零向量"的残缺态，直到检索时才炸。根因是三层 fail-open 叠加：①`ingest/runtime.store_document` 先提交 chunk+FTS、后逐 chunk 向量化，embedding 失败时残缺文档已落库；②`sync_planner.execute_sync_plan` 逐文件裸 `except Exception: failed += 1` 吞异常——不 log、不留错误文本（违反"不吞异常"红线）；③worker 拿到 `failed>0` 的 summary 照样 `mark_done`、`last_error` 空。local 目录、Google Drive、Confluence 全部同步源走同一条路径，全部受影响。

## What Changes

- **①ingest 原子化（embed-before-commit）**：`store_document` 改为先在内存完成**全部 chunk 的向量化**，全部成功后才执行 `replace_document`（chunk+FTS 提交）与向量 upsert——embedding 故障 = 整文档干净失败，库里不留任何半成品（chunk 数十级、内存可接受）。
- **②吞错点改为记录**：`execute_sync_plan` 的逐文件 except 改为结构化 `log.exception` + 按文件收集**脱敏后的错误文本**（经 `structured_logging.redact_text`，防 connector 异常内嵌凭据），随 summary 返回（新增 errors 字段，带上限截断）。
- **③worker 终态判定**：sync 类 job（`sync_directory` / `connector_sync`）完败（`failed > 0 ∧ ingested == 0 ∧ scanned > 0`，典型 = embedding 挂）时 SHALL 落 **failed 终态**并带错误摘要；部分失败仍 done，但 `last_error` 记录失败明细摘要（done + last_error 非空 = 部分失败语义，复用既有列，无迁移）。错误经既有 kb-serve `GET /status`（近期 job 含 status/last_error）对运维可见。
- 验收必含 dogfooding 复现场景：embedding 404 时上传 → job 落 failed 带错误、文档不出现在列表、库中无 chunk 残留。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `knowledge-base`：Manual text ingest and chunk indexing 增加原子性约束——向量化先于任何持久化写；embedding 失败时不产生 document/chunk/FTS 任何残留。
- `kb-ingest-worker`：新增 sync job 失败可观测与终态语义 requirement（逐文件错误必须记录与脱敏、完败落 failed、部分失败 done+last_error），与既有 reindex 失败落终态的措辞对齐。

## Impact

- **Owning package**：`fleetent.knowledge_base`（`ingest/runtime.py`、`sync_planner.py`、`worker.py`）+ 对应测试。
- **Public API surface**：无 HTTP 端点变化；`SyncExecutionSummary`/`SyncResult` 增加 errors 字段（向后兼容默认空）；job 语义变化经既有 `/status` 暴露。
- **Owned tables / migrations / config namespace**：均无（`kb_ingest_jobs.last_error` 列已存在）。
- **Cross-module dependencies**：新增 `knowledge_base → structured_logging.redact_text`（顶层基础设施，方向合法）。
- **Migration / shim plan**：无。行为变化：过去"静默 done"的完败 job 升级后落 failed——这是修复目标本身；存量残缺文档（有 chunk 无向量）不自动修复，运维用 `fleetent kb reindex` 重建（已有通路）。
- **切片终审**：文件面与在途 change 零交叠。
