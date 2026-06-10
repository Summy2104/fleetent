## 1. 安全网（删前先锁活路径 + 确认死路径可删）

- [ ] 1.1 写/确认 characterization 测试见绿：活路径端到端——`agent_kbs_store.bind` → `materialize._knowledge_for_agent` 产出 `AgentKnowledge` → `long_term_ctx` 读 `agent.knowledge` → `kb_ids` → `retrieval.search`；断言此路径**不依赖** `resolve_agent_kb_ids`
- [ ] 1.2 写守护断言见绿：`knowledge_base_agent_bindings` 在 src 无写入路径（无 INSERT/UPDATE/REPLACE）、`resolve_agent_kb_ids` 在 src 无活调用方（仅 export/test）——确认可安全删

## 2. drop 死表（alembic）

- [ ] 2.1 写迁移测试见红：`alembic upgrade head` 后 `knowledge_base_agent_bindings` 表不存在
- [ ] 2.2 新增 alembic 迁移 drop `knowledge_base_agent_bindings`，跑绿 2.1（无数据迁移——本就无写入）

## 3. 删死代码

- [ ] 3.1 写/调测试见红：从 `fleetent.knowledge_base` / `retrieval` 导入 `resolve_agent_kb_ids` / `list_agent_kb_bindings` / `AgentKnowledgeBaseBinding` 应失败（死符号已移除）
- [ ] 3.2 删 `knowledge_base/bindings.py`（死路径）、`knowledge_base/retrieval/scope.py`（仅 re-export 死路径）及 `knowledge_base/__init__.py`、`retrieval/__init__.py` 的相关导出，跑绿 3.1
- [ ] 3.3 跑既有 KB / long-term-ctx 单测确认无残留引用、活路径行为不变

## 4. 处理自测死路径的测试

- [ ] 4.1 删除 `tests/integration/test_knowledge_base_agent_bindings.py`（整测死路径，且依赖已 drop 的表）
- [ ] 4.2 删除/重指向 `tests/unit/test_knowledge_base_retrieval_contracts.py` 中针对 `scope.resolve_agent_kb_ids` 的签名断言（指向活路径或移除）

## 5. 收尾、护栏与门禁

- [ ] 5.1 全仓 grep 确认 `resolve_agent_kb_ids` / `knowledge_base_agent_bindings` 引用归零（spec 已在本 change 校正）；不得 `import fleetent.platform.*`
- [ ] 5.2 跑 `scripts/check_test_layers.py` + 依赖护栏；确认 `agent_kbs`/`materialize`/`long_term_ctx` 活路径未被波及
- [ ] 5.3 change 收尾：`make test-pr` 全绿 + `uv run pytest tests/integration -q` 对照 main 基线无新增失败 + `openspec validate drop-dead-kb-binding-path --strict`
