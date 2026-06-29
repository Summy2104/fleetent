## 1. 正式化契约 + 抽默认 LocalKnowledgeProvider

- [ ] 1.1 写 integration 测试:默认(未注入)provider 下,KB 检索结果与现 `_search_knowledge` 本地分支等价——含 use_planner=false(search mode)与 use_planner=true(plan+execute)两路(见红/对照基线)
- [ ] 1.2 写 unit 测试:`KnowledgeProvider` 契约类型为 `(Principal, str, list[str], int, KBRetrievalAuditContext|None) → Awaitable[list[KnowledgeChunk]]`(见红)
- [ ] 1.3 改 `KnowledgeProvider` 类型 + 把本地检索逻辑(读 retrieval_policy、planner/search)抽成默认 `LocalKnowledgeProvider`,接收 `(principal, query, kb_ids, limit, audit)`、返回 `list[KnowledgeChunk]`;跑 1.1–1.2 见绿

## 2. 作用域解析留 long-term-ctx,经契约传入

- [ ] 2.1 写 integration 测试:`_search_knowledge` 解析 enabled/bindings→kb_ids/tenant,构造 Principal,以完整契约调当前 provider;空范围短路不调 provider(见红)
- [ ] 2.2 写 integration 测试:注入自定义 provider 时,收到的入参含 principal(tenant+user)、解析后的 kb_ids、透传的 audit(见红)
- [ ] 2.3 重构 `_search_knowledge`:统一为"解析 scope → 调当前 provider"(消除 provider 分支/本地分支两套);默认 provider 始终设;跑 2.1–2.2 见绿

## 3. 失败优雅降级

- [ ] 3.1 写 integration 测试:注入的 provider 抛异常 → long-term-ctx 记日志、该路径降级空,`build_context` 不抛、memory/always-facts 仍返回(见红)
- [ ] 3.2 写 integration 测试:provider 超时 → 同样降级空(见红)
- [ ] 3.3 确认/补全失败降级:`_retrieve_with_timeout` 或 provider 调用处覆盖异常+超时;跑 3.1–3.2 见绿

## 4. 收尾验证

- [ ] 4.1 跑 `make test-pr` + `make test-unit-ci`(含 76% 覆盖率关)+ `make test-integration-ci`,判"对照 main 基线无新增失败、覆盖率不破 76"
- [ ] 4.2 ruff format/check 改动文件;module-boundaries 检查通过(long_term_ctx 仍 ✗→ platform);`openspec validate harden-kb-provider-seam` 通过
- [ ] 4.3 更新 `docs/capabilities/` 相关文档:KnowledgeProvider 硬契约、默认 LocalKnowledgeProvider、注入替换、失败降级(非代码产物,人工确认后再 commit)
