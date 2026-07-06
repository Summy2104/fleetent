# kb-ingest-fail-closed — Design

## Context

写路径现状：`store_document`（`ingest/runtime.py`）顺序为 `_ensure_kb_embedding_identity` → `store.replace_document`（SQL：document+chunk+FTS，事务内提交）→ 逐旧 chunk 删向量 → 逐新 chunk `_upsert_chunk`（`backend.upsert(id, await vector_store.embed_text(content), ns)`）。embedding 在**最后一步**才发生，失败时 SQL 已提交。上层 `execute_sync_plan`（`sync_planner.py:235`）对每文件裸 `except Exception: failed += 1`，异常与错误文本双双丢失；worker 对 sync 类 job 无条件 `mark_done`。三层叠加 = 残缺态 + 零可观测。

可复用件：`structured_logging.redact_text`（2026-07-06 落地的公开脱敏 API，connector 异常文本可能内嵌 token）；`kb_ingest_jobs` 表已有 `last_error` 列且 kb-serve `GET /status` 已读它；worker 对 job handler 抛出的异常已有 `mark_failed` 通路（`worker.py:404`）。

## Goals / Non-Goals

**Goals:**

- embedding 故障时**库中零残留**：不产生 document/chunk/FTS/向量任何一件半成品；重复导入（overwrite 语义）时旧文档保持原样。
- 每个失败文件的错误**必被记录**（结构化日志 + 脱敏文本进 summary），完败 job 落 failed 终态，部分失败在 done 上带 `last_error` 明细——运维经既有 `/status` 即可诊断。
- 三个同步源（local / google_drive / confluence）与手动 ingest 同享修复（都收敛在 `store_document` 与 `execute_sync_plan`）。

**Non-Goals:**

- 不做跨 SQL/向量两库的分布式原子性（见 D1 的窗口说明）。
- 不做存量残缺文档的自动检测/修复（`kb reindex` 已是重建通路；检测属观测面后续批次）。
- 不动上传端点/UI 反馈形态（`/status` 已够运维诊断；UI 呈现属 admin 观测面批次）。
- 不改 job 队列 schema。

## Decisions

**D1 — 原子性方案：embed-before-commit，而非失败补偿删除。**
`store_document` 重排为：先对全部新 chunk 串行调 embedding 得到向量列表（纯内存，不触任何库）→ 全部成功后才 `replace_document` + 删旧向量 + 逐 chunk `backend.upsert(id, vector, ns)`（不再边 upsert 边 embed）。embedding 是压倒性主故障源（网络/模型服务），把它挪到任何写之前，故障即整文档干净失败。替代方案——失败后补偿删除已提交文档：补偿本身可能再失败（同一故障窗口），且 overwrite 场景下旧文档已被 replace 破坏、无从恢复，拒绝。**残余窗口**：向量化成功后、SQL 已提交、向量 upsert（本地 sqlite 写）失败——概率远低于 embedding 故障且此时异常会正常上抛（②不再吞）→ job 落 failed 可见，接受并记录于此。

**D2 — 吞错点改造：log + 脱敏收集，不改变"单文件失败不中断整批"的语义。**
`except Exception as exc:` → `_logger.exception("kb_sync_file_failed", source_path=...)` + `errors.append((source_path, redact_text(str(exc))))`；`SyncExecutionSummary` / `SyncResult` 增加 `errors: list`（默认空，向后兼容），收集数量设上限（如 10 条，超出计数截断）防超长 payload。逐文件容错保留——部分失败不该拖死整批（与 reindex "单失败不影响其它 job" 同哲学）。

**D3 — worker 终态判定：完败 failed、部分失败 done + last_error。**
`sync_directory` / `connector_sync` 分支拿到 summary 后：`failed > 0 ∧ ingested == 0 ∧ scanned > 0` → 抛携带首条错误摘要的异常，走既有 `mark_failed` 通路（`last_error` 落库）；`0 < failed < scanned 或 ingested > 0` → 照常 `mark_done`，但把错误明细摘要写入 `last_error`（done + last_error 非空 = 部分失败，复用既有列与 `/status` 读面，零迁移）。替代方案——新增 job 状态枚举 `partial`：动 schema 与全部消费方，收益不抵，拒绝。

**D4 — 错误文本一律过 `redact_text` 再持久化。**
connector 异常（Google Drive / Confluence 鉴权失败等）可能内嵌 token/URL 凭据；`operations.py` 的 check/sync 路径已有此纪律，本 change 把 sync_planner 路径对齐。

## Risks / Trade-offs

- **[embed-before-commit 增加内存持有]** 文档级 chunk 数十量级 × 千维向量，单文档 MB 级以内 → 接受；超大文档如成为问题属 chunking 策略议题。
- **[行为变化：过去静默 done 的完败 job 变 failed]** 这是修复目标；定时 connector sweep 的完败 job 会开始显式 failed——运维可见性提升，无自动重试风暴（队列 max_attempts 语义不变，确认测试覆盖）。
- **[errors 字段消费方兼容]** summary 序列化进 job result/日志的既有消费方按新增可选字段处理；测试覆盖空/非空两态。

## Migration Plan

无 DB 迁移。升级即生效。存量残缺文档（有 chunk 无向量）不自动修复——运维排查（playbook §2 第 7 步向量核查）后 `fleetent kb reindex` 重建。回滚 = 回退版本，无数据兼容问题。

## Open Questions

- 残缺文档的**存量检测**（chunk 数 > 0 ∧ 向量数 == 0 的 KB 级审计）值不值得做成 `kb doctor` 类命令——留给 KB 观测面批次。
