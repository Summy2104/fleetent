## 边界（先读）
只动 `knowledge_base/serve.py`、`knowledge_base/runtime.py`(透传)、`long_term_ctx/__init__.py` 的 HttpKnowledgeProvider 请求体区域。
**严禁碰**(B 的地盘):`retrieval/search.py`、`core/migrations.py`、`core/store.py`、`vector_store/runtime.py`、`ingest/runtime.py`、`agent_config.py`、`kb-service.yaml.example`、`long_term_ctx` 的 `_retrieve_with_timeout`。

## 1. serve.py /search 接收策略（TDD）

- [ ] 1.1 测试先行：`SearchRequest` 含可选 `mode` / `rerank` / `use_planner`(默认 default_mode/False/False);未带时行为同现状。见红
- [ ] 1.2 实现：`serve.py` 的 `SearchRequest`(:40)加 `mode: str | None`、`rerank: bool = False`、`use_planner: bool = False`
- [ ] 1.3 测试先行：请求带 `rerank=true`+`mode=hybrid` → handler 以 rerank+hybrid 调 `kb_runtime.search`(不再 `rerank=False`)。见红
- [ ] 1.4 实现：handler(:183-195)去掉硬编码 `rerank=False`/`mode=config.default_mode`,改取自请求(mode 缺省回落 `config.default_mode`)

## 2. serve 跑 planner（TDD）

- [ ] 2.1 测试先行：请求 `use_planner=true` → 经 `plan_knowledge_search` + `execute_knowledge_search_plan` 执行(镜像 long_term_ctx:239-251 的 Local 逻辑),返回融合结果。见红
- [ ] 2.2 实现：handler 内 `use_planner` 为真时走 planner public API;否则走 `kb_runtime.search`。planner 经 `knowledge_base` public API 调用,不复制检索逻辑
- [ ] 2.3 `rerank` 非 hybrid 的约束沿用 `knowledge_base.search` 既有行为(一致报错/忽略,不静默错)

## 3. HttpKnowledgeProvider 发全字段（TDD，只改请求体区域）

- [ ] 3.1 测试先行:HttpKnowledgeProvider 把 agent policy 的 `mode`/`rerank`/`use_planner` 放进 `/search` 请求体。见红
- [ ] 3.2 实现：`long_term_ctx/__init__.py` 的 HttpKnowledgeProvider 请求构造处加这三字段(从 policy 取);**不碰** `_retrieve_with_timeout` 等其它区域

## 4. 收尾门禁

- [ ] 4.1 `openspec validate kb-http-quality-passthrough --strict`
- [ ] 4.2 `make test-pr` + `make test-integration-ci` 全绿
- [ ] 4.3 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py`（未碰 platform）
- [ ] 4.4 `git diff --name-only main` 自查：只出现 serve.py / knowledge_base/runtime.py / long_term_ctx/__init__.py / kb-read-service spec —— **不应出现 B 的文件**
- [ ] 4.5 功能分支 `openspec archive kb-http-quality-passthrough`（同步 kb-read-service spec）
- [ ] 4.6 所有 checkbox 标 `[x]`
