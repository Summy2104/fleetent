## 1. memory 向量后端注入口

- [x] 1.1 写测试（integration）：注入一个 per-agent 向量后端后，memory 的 upsert/search/delete 经它落库；未注入时按基线行为（报错/降级，与 store 一致） —— 见红
- [x] 1.2 `memory/store.py`（或 `__init__`）：加 per-agent 向量后端注入口（倾向独立 `set_vector_backend`，不破坏现有 `set_state_db` 签名）+ `_memory_backend()` 取注入后端 —— 见绿

## 2. 去全局 vector_store 旁路、改注入后端（embedding 仍全局，namespace 保留）

- [x] 2.1 写测试（integration）：`search("user-1", q)` 经注入后端按 `mem:user-1` namespace 检索（先 `vector_store.embed_text` 嵌入），不调用全局 `vector_store` backend search；顺序/过期/缺失 id 行为不变 —— 见红
- [x] 2.2 `memory/search.py`：`vector_store.search(q, ns, limit)` → `embed_text(q)` + `_memory_backend().search(query_vector, ns, limit)` —— 见绿
- [x] 2.3 `memory/operations.py` / `extraction.py` / `maintenance.py`：`vector_store.upsert/delete(..., memory_namespace(user_id))` 改为先 embed（upsert 时）再 `_memory_backend().upsert/delete(...)`，namespace 保留 —— 见红→见绿
- [x] 2.4 grep 自查 + 护栏测试：memory 模块无全局 `vector_store.{search,upsert,delete}` 旁路（`embed_text` 除外）

## 3. boot 接线（agent 读 + 写都经本 agent 的 agent_vectors.db）

- [x] 3.1 写测试（integration）：agent boot 后，memory 向量落本 agent 的 `<tenant>/<agent_id>/agent_vectors.db`；多 agent 下 A 的向量 B 够不到 —— 见红
- [x] 3.2 `runtime/agent_app.py`：注入 `agent_scope(tenant, agent_id).vector_backend` 给 memory（与 `set_state_db` 同处 boot 注入点） —— 见绿

## 4. 文档与收尾

- [x] 4.1 同步 `docs/architecture/data-model.md` §3.6：memory 向量 = per-agent `agent_vectors.db`（不再是全局 vector_store + namespace）
- [x] 4.2 同步 `docs/capabilities/memory.md`（如有提及向量存储处）：memory 向量经注入的 per-agent backend
- [x] 4.3 验证基线：无 platform 时 memory 检索经注入后端正常；`fleetent agent run` 多轮记忆召回正常
- [x] 4.4 change 收尾：`make test-pr` 全绿 + `uv run pytest tests/integration -q`（对照 main 基线，无新增失败）
