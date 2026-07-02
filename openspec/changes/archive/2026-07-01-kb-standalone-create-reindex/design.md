## Context

命令目录审计后收命令侧的两类账：缺失（standalone 无建库/重建）+ 冗余空壳（平台 `kb sync`/`vector reindex` no-op）。纯命令层，不碰 HTTP API（⚡ 检索归属另议）。新命令走 `kb <verb>`（对齐已落地的 kb-cli-verb-grouping）。真实原语都已存在：`create_knowledge_base`、`vector_store.reindex()`、kb-worker 的 job 分派与 `connector_sync` 类型。

## Goals / Non-Goals

**Goals**
- standalone `kb create`（幂等建库，无 platform）。
- standalone `kb reindex`（入队 → kb-worker 重建向量，守单写者）。
- 退平台两个 no-op 空壳（kb sync / vector reindex）。

**Non-Goals**
- 不碰 HTTP API / 检索归属（⚡）。
- 不加 `kb sync`（sweep 自动同步够用）。
- 不做非 KB 的通用向量 reindex。

## Decisions

**D1：`kb reindex` 入队,不直调。** reindex 写 `kb_vectors.db`——按 KB 单写者铁律,只有 kb-worker 能写。故 `kb reindex` 入队 `reindex` job,worker 消费执行(与 `kb ingest`/`kb extract` 同形)。直调会在 worker 运行时造成双写者,否决。`--wait` 轮询终态,复用 ingest/extract 的轮询工具。

**D2：worker 新增 `reindex` job 分支,复用 `vector_store.reindex()` 公共 API。** 在 worker.py 现有 `if job_type == "..."` 链末（`extraction` 之后、`unknown` raise 之前）加 `reindex` 分支：由 job 的 `kb_id`/`tenant_id` 构造 `ReindexRequest`（owner/namespace 经 `vector_store.namespaces` 取该 KB 的向量命名空间,source items = 该 KB 在 `kb.db` 的存量 chunk),调 `reindex()` 重建。**关键接线**：namespace 必须与 ingest 写向量时用的**同一命名空间**,否则重建到错误 namespace。apply 时以 ingest 侧写向量的命名空间为准（读 ingest/runtime + vector_store.namespaces 对齐）。

**D3：`kb create` 幂等,经配置同源建库。** 复用 kb-ingest/extract 的 config 解析（`load_kb_service_config` → tenant_id/data_dir → `_knowledge_database`）,调 `create_knowledge_base`（内部 `ensure_knowledge_base`,已幂等）。已存在则 no-op 成功（打印现状）。不依赖 platform。

**D4：退空壳 = 纯删除,无功能损失。** `run_kb_sync`/`reindex_vector` 是 no-op（只记 trace）,删之不丢任何真实行为。真同步在 kb-worker `connector_sync` + sweep;真重建现由 `kb reindex` 承接。`manual-maintenance-entrypoints` 的 "Vector rebuild" 场景移除（其"用 vector store 公共 reindex API"的意图现由 worker reindex 分支落实,已在 kb-ingest-worker spec 表达）。

## Risks / Trade-offs

- **reindex namespace 接错** → 重建到与 ingest 不一致的命名空间,检索读不到。缓解：apply 必须对齐 ingest 侧写向量的命名空间来源;加 e2e——ingest → 删/重建 vectors → `kb reindex --wait` → 检索仍命中。
- **reindex 是重操作**（re-embed 所有 chunk）→ 大 KB 慢;`--wait` 用较宽超时,或不 wait 只入队。命令打印 job id 便于查 `/status`（经 kb-serve）。
- **退平台空壳的测试** → `test_coverage_closure_helpers.py` 对 `run_kb_sync`/`reindex_vector` 的断言删除;确认无其它引用。

## Migration Plan

无数据迁移。脚本调 `platform maintenance vector reindex` → 改 `fleetent kb reindex --config <yaml> --kb <id>`;`kb sync` 无替代（sweep 自动同步）。回滚 = revert。

## Open Questions

无（reindex 的 namespace 具体来源在 apply 时以 ingest 侧实现为准对齐,非设计悬念）。
