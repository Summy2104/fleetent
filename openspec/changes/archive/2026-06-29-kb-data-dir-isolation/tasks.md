## 1. 路径 helper + 路由解析到 kb/

- [x] 1.1 写 integration 测试:`SQLiteTenantBackend.resolve(t)` 解析 KB 关系库/向量库到 `tenants/<t>/kb/kb.db` 与 `kb/kb_vectors.db`;多租户物理隔离仍成立(见红),`tmp_path` 隔离绝不碰 data/
- [x] 1.2 在 `paths.py` 加 `tenant_kb_dir(tenant_id) = tenant_dir(t)/"kb"`(单一来源);unit 覆盖
- [x] 1.3 改 `tenant_router.SQLiteTenantBackend.resolve`:kb.db/kb_vectors.db 路径经 `tenant_kb_dir`,幂等 `mkdir kb/`;跑 1.1 见绿
- [x] 1.4 grep 全仓 `'kb.db'`/`"kb.db"`/`kb_vectors` 字面量,把残留的直接拼接点导向 `tenant_kb_dir`

## 2. 存量扁平布局幂等迁移

- [x] 2.1 写 integration 测试:租户根存在 legacy 扁平 `kb.db`(+wal/shm)/`kb_vectors.db` 且无 `kb/` → 解析/建库前移入 `kb/`;迁移幂等(重复执行不破坏);迁移后可正常开库读写(见红)
- [x] 2.2 实现"开库前"幂等迁移(`kb/` 不存在且根有 `kb.db` 时 mkdir + move kb.db/-wal/-shm/kb_vectors.db 入 kb/),在 `resolve` 与 `_prepare_tenant_kb` 建连接前调用;跑 2.1 见绿
- [x] 2.3 写 integration 测试:无 platform / standalone `agent run` 路径下也经同一迁移+解析到 `kb/` 并可读写(基线不破)(见红→绿)

## 3. node 挂 kb/ 整目录(修 WAL)

- [x] 3.1 写 integration 测试:`_prepare_tenant_kb` 在 `tenants/<t>/kb/` 下建 kb.db/kb_vectors.db(见红)
- [x] 3.2 改 `node/backend.py`:`_prepare_tenant_kb` 建到 `kb/`;RO 挂载从 kb.db+kb_vectors.db 两条文件 → `_bind_mount(tenant_kb_dir(t), read_only=True)` 一条目录挂载(含 -wal/-shm);跑 3.1 见绿
- [x] 3.3 验证 agent 容器经目录 RO 挂载仍能读 KB、且读到最新提交(WAL 一致;有 live/managed 烟测则在其中验)

## 4. 收尾验证

- [x] 4.1 跑 `make test-pr` + `make test-unit-ci`(含 76% 覆盖率关)+ `make test-integration-ci`,判"对照 main 基线无新增失败、覆盖率不破 76"
- [x] 4.2 ruff format/check 改动文件;module-boundaries / tenant-routing 护栏通过;`openspec validate kb-data-dir-isolation` 通过
- [x] 4.3 更新 `docs/architecture/agent-home-layout.md` 目录树(KB 收进 `tenants/<t>/kb/`,node 整目录挂载)(非代码产物,人工确认后再 commit)
