## Why

memory 的**关系侧**已 per-agent 物理隔离(`memory_items` → `agent_state.db`，`set_state_db` 注入，且去掉了 namespace 列),但**向量侧没跟上**:`search.py` / `operations.py` / `extraction.py` / `maintenance.py` 全部用**全局 `vector_store` + `mem:{user_id}` namespace**,而非 per-agent `agent_vectors.db`。

- `agent_scope(tenant, agent_id)` **提供** `AgentScope.vector_backend`(对应 data-model 的 `agent_vectors.db`),但 `agent_vectors` 全仓只在 `tenant_router` 出现——**没人用**(和 X 之前 `KbScope.kb_vector_backend` 被丢弃一模一样)。
- 后果:多 agent 的记忆向量挤在一个**全局向量文件**里靠 namespace 分,**无物理隔离**;`agent_vectors.db` 是建了没人用的空壳。与关系侧(物理隔离)不一致,也违反 #3 的物理分区模型。
- **shared memory 是正面参照**:它已注入 `shared_memory_vector_backend`、用注入后端 + namespace(`shared:`)——这套接法现成,memory 照搬即可。

## What Changes

把 memory 向量接到 per-agent `agent_vectors.db`(mirror shared memory 的做法):

- **注入口**:memory 加 per-agent 向量后端注入口(随 `set_state_db` 一并传,或单独 setter)。
- **boot 接线**:`agent_app` 把 `agent_scope(tenant, agent_id).vector_backend`(`agent_vectors.db`)注入 memory。
- **去全局旁路**:`search` / `operations` / `extraction` / `maintenance` 的 `vector_store.{search,upsert,delete}(..., memory_namespace(user_id))` 改用**注入的 per-agent backend**——embedding 仍用全局 provider(`vector_store.embed_text`),但 upsert/search/delete 落注入后端;`mem:{user_id}` namespace **保留**为该 per-agent 向量库内的按用户分区(与 shared memory 一致)。
- **护栏**:memory 模块无全局 `vector_store.{search,upsert,delete}` 旁路(embed_text 除外)。

不在本切片:KB 向量(X 处理);memory 数据迁移(无存量真实数据 → 新建/重 index)。

## Capabilities

### New Capabilities
<!-- 无;落实既有 per-agent 物理隔离到向量侧 -->

### Modified Capabilities
- `memory-layer`: memory 向量同步与语义检索改经**注入的 per-agent 向量后端**(`agent_vectors.db`，来自 `agent_scope.vector_backend`),不再用全局 `vector_store` backend;`mem:{user_id}` namespace 保留为 per-agent 向量库内分区,embedding 仍用全局 provider。

## Impact

- **代码**:`memory/store.py`(或 `__init__`,加向量后端注入口)、`memory/search.py` / `operations.py` / `extraction.py` / `maintenance.py`(去全局 `vector_store` 旁路、用注入后端)、`runtime/agent_app.py`(注入 `agent_scope.vector_backend`)。
- **owned tables**:`agent_vectors.db`(per-agent)现被真正使用(此前空壳);关系侧 `agent_state.db` 不变。
- **config namespace**:无;**cross-module**:`tenant_router`(`AgentScope.vector_backend`)、`vector_store`(仅 `embed_text` 嵌入 provider)。
- **migration/shim**:无数据迁移(无存量真实数据;如有需重新 index 到 per-agent backend)。
- **验证基线**:多 agent 下,A 的记忆向量落 A 的 `agent_vectors.db`、B 落 B 的,物理隔离;无 platform 时 memory 检索仍经注入的 per-agent backend。
