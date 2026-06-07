> 前置：阶段1（vector_store 顶层）已合并。每个实现 task 严格 TDD（红→绿→可选 refactor）。

## 1. 依赖护栏 + 结构契约（TDD 红先行）

- [ ] 1.1 写失败测试：断言 `fleetent.knowledge_base` 顶层包存在且有 `core`/`retrieval`/`ingest`/`management` 四子包（此时不存在 → 红）（`tests/unit/`，纯 import 静态检查）
- [ ] 1.2 写失败测试：断言护栏边——`knowledge_base.retrieval` ✗→ `knowledge_base.ingest`；`knowledge_base.core` ✗→ `retrieval`/`ingest`/`management`；`knowledge_base`（含子包）✗→ `fleetent.platform`（此时结构未建 → 红）

## 2. core：Readable / Writable Protocol（TDD）

- [ ] 2.1 写失败测试：断言 `knowledge_base.core` 暴露 `KnowledgeReadable` / `KnowledgeWritable` 两个 Protocol，且 `KnowledgeStore` 同时满足两者（mypy/`isinstance`-via-`runtime_checkable` 或结构断言）
- [ ] 2.2 `git mv` store.py/models.py → `knowledge_base/core/`；抽 `KnowledgeReadable`（读方法）/`KnowledgeWritable`（写方法）Protocol，`KnowledgeStore` 单实现两者
- [ ] 2.3 跑第 2 组测试 → 绿

## 3. retrieval：只读边界（TDD）

- [ ] 3.1 写失败测试：断言 `retrieval` 的 `search`/`graph_search`/`scope` 公共函数签名只接受/返回 `KnowledgeReadable`，且 retrieval 不暴露任何 KB 内容写接口（D3 写入单一化）
- [ ] 3.2 `git mv` 搬迁：`runtime.py` 的 search 系（`search`/`_search_vector`/`_search_hybrid`/rerank helpers）、`graph_search.py`、`bindings.py` 的 `resolve_agent_kb_ids`/`_get_binding` → `knowledge_base/retrieval/{search,graph_search,scope}.py`；签名改为依赖 Readable
- [ ] 3.3 跑测试 → 绿

## 4. ingest：唯一内容写 + settings 注入（TDD）

- [ ] 4.1 写失败测试：断言 ingest 摄取入口接收注入的 `KnowledgeBaseSettings`、不自读家目录 `_kb_config`；KB 内容写（ingest/delete/archive document、图谱抽取）只经 ingest
- [ ] 4.2 搬迁：`runtime.py` 的 `ingest_text`/`ingest_parsed`/`_ingest_chunks`/`delete*`/`archive*`、`connectors/*`、`parsers.py`、`extraction.py`/`extraction_store.py`、`planner.py`/`sync_planner.py`、`config.py` → `knowledge_base/ingest/`
- [ ] 4.3 ingest 对外入口改为接收 settings 纯函数 + 新增 `as_knowledge_base_settings` adapter（消解 connector 双源）
- [ ] 4.4 跑测试 → 绿

## 5. management：容器/绑定写（TDD）

- [ ] 5.1 写失败测试：断言 `management` 暴露建库/归档/改描述/list + agent↔KB 绑定写接口，依赖 Writable
- [ ] 5.2 搬迁：`runtime.py` 的 `create_knowledge_base`/`update_knowledge_base_description`/`archive_knowledge_base`/`list_knowledge_bases`/`list_documents`、`bindings.py` 的 `bind/unbind/list_agent_kb_bindings` → `knowledge_base/management/`
- [ ] 5.3 跑测试 → 绿

## 6. shim + 调用方迁移

- [ ] 6.1 旧路径 `intelligence/knowledge_base/__init__.py` 留 re-export shim（旧公共符号全可达）
- [ ] 6.2 迁 agent 侧调用方 `long_term_ctx` → `knowledge_base.retrieval`
- [ ] 6.3 迁 platform 调用方 `knowledge_base_management/kb_admin_api`、`admin_cli` → `knowledge_base.ingest`/`.management`，并改为向 ingest 注入 settings（`as_knowledge_base_settings`）
- [ ] 6.4 全仓 grep 确认无残留硬编码 `intelligence.knowledge_base`（shim 除外）
- [ ] 6.5 跑第 1 组护栏测试 → 绿
- [ ] 6.6 `uv run pytest -x -q` → 全绿

## 7. 解耦基线验证

- [ ] 7.1 验证 agent 在「无 platform、platform 表不存在」环境下，`fleetent agent run` 对话 + KB 检索（经 `retrieval`）正常工作（集成测试或 smoke）

## 8. 收尾

- [ ] 8.1 `uv run ruff format src tests && uv run ruff check src tests`
- [ ] 8.2 `uv run mypy src`（Readable/Writable Protocol 类型隔离验证）
- [ ] 8.3 `uv run python scripts/check_test_layers.py`
- [ ] 8.4 `uv run pytest -x -q`（全量绿）

> shim 删除时机：本 change 末尾或阶段5 统一收口（见 design §Open Questions）。
