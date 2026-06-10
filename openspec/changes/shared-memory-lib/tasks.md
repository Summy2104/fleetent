## 1. tenant_scope 扩展 + 共享库 MIGRATIONS

- [ ] 1.1 写失败测试：`tenant_scope(T)` 返回共享记忆关系句柄 + `shared:` 向量后端，映射 `<T>/shared_memory.db` + `shared_memory_vectors.db`；agent 取读写连接
- [ ] 1.2 实现：tenant_scope 加共享记忆句柄 + 后端路径；shared_memory DDL lift 进 per-tenant 共享库 `MIGRATIONS`，跑绿 1.1

## 2. shared.py 连接走 tenant_scope

- [ ] 2.1 写失败测试：`memory/shared.py` 连接来自 `tenant_scope`；护栏断言无自连接全局库；`shared:` 向量路由到共享记忆向量库
- [ ] 2.2 实现：shared.py 连接走 tenant_scope（读写）+ 向量路由，跑绿 2.1

## 3. 多写并发（依赖 WAL）

- [ ] 3.1 写测试：同主体两连接并发写 shared_memory.db，WAL + busy_timeout 下均成功、读不阻塞（需 `sqlite-wal-concurrency` 已落地）
- [ ] 3.2 跑既有 shared memory 单测/检索确认行为不变

## 4. 收尾

- [ ] 4.1 不得 import platform、named params、无新增裸 sqlite3.connect；依赖护栏
- [ ] 4.2 `make test-pr` 全绿 + `uv run pytest tests/integration -q` 对照 main 基线无新增失败 + `openspec validate shared-memory-lib --strict`
