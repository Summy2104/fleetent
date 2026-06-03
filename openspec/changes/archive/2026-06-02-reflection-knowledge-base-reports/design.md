# Design

## Scope

KB reflection report 是租户或 KB scope 的只读质量报告。它分析已有运行证据和 KB 状态，输出结构化 findings：

- 缺知识；
- 文档可能过期；
- 检索质量低；
- connector 同步异常；
- entity / graph 覆盖不足。

第一版不做 mutation proposal，因为 KB 的修复动作通常涉及补文档、改 connector scope、重新同步、删除过期文档，
这些动作需要管理员理解来源和影响后手动处理。

## Inputs

只通过 public API 读取：

- observability：query trace events、source attribution、zero-result / low-confidence / user correction 迹象；
- knowledge-base：search / graph_search 的只读能力、connector latest status、KB/doc summary；
- entity/graph：若 entity extraction 或 graph search 尚未实现，相关 finding 类型可返回 skipped/insufficient_signal。

不得直接查询 `knowledge_documents`、`knowledge_chunks`、connector state 或 trace table。

## Finding Model

`KnowledgeBaseReflectionFinding`：

- `id`
- `type`
- `severity`: `low`、`medium`、`high`
- `tenant_id`
- `kb_ids`
- `affected_resource`: kb/document/connector/topic/entity
- `summary`
- `evidence_refs`
- `recommendation`
- `metadata`

Evidence 只保存 ids、短摘要和脱敏 metadata，不保存完整用户 transcript 或完整文档正文。

## Detection Rules

第一版使用 deterministic rules：

- `missing_knowledge`：同类 query 多次出现 zero-result、low-source-attribution 或 forbidden fallback；
- `stale_document`：被引用文档与近期 query / connector metadata 存在明显时间冲突，或长期未被召回且 connector 显示来源已更新；
- `low_retrieval_quality`：同一 topic 多次 top result score 低、用户追问“不是这个”或 source attribution 缺失；
- `connector_sync_issue`：connector latest status failed/stale，或连续 failed count 超阈值；
- `entity_graph_gap`：关系型 query 无 graph evidence，或 entity extraction coverage 低。

## Persistence

`kb_reflection_reports` 保存 report summary、finding payload、scope、time_window、created_at。payload 不保存完整
transcript 或文档正文。

## Evaluation

默认 evaluation 使用 fake observability events、fake connector status、fake KB signals：

- expected findings 出现；
- forbidden findings 不出现；
- persisted payload 不包含 raw transcript / document snippets；
- KB unavailable 时 report 不失败，只记录 insufficient signal。
