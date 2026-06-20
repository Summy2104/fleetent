## 1. 队列表迁移

- [ ] 1.1 [测试] integration:对空库 `alembic upgrade head` 后断言存在 `kb_ingest_jobs` 表及字段(id/tenant_id/kb_id/connector_ref/cred_ref/status/attempts/时间戳)→ 红
- [ ] 1.2 [实现] Alembic 迁移建 `kb_ingest_jobs`(管理库;**迁移版本号 apply 时取 `uv run alembic heads` 续号,勿硬编码**)
- [ ] 1.3 [验证] 运行该 integration 测试 → 绿

## 2. 队列 store(入队 / claim / done / retry)

- [ ] 2.1 [测试] integration:`enqueue` 产生 pending;`claim` 原子取一(并发不重复);`done`/`failed+retry`(attempts 上限)→ 红
- [ ] 2.2 [实现] 队列 store(经 `db.py` 边界,named params),提供 enqueue/claim/mark_done/mark_failed;claim 原子 UPDATE
- [ ] 2.3 [实现] 入队时读 connector 注册表,写非密 `connector_ref` + `cred_ref`(Vault 引用),**不写明文**
- [ ] 2.4 [验证] `uv run pytest tests/integration/test_kb_ingest_queue.py -x -q` → 绿

## 3. 触发器改造(同步内联 → 入队)

- [ ] 3.1 [测试] integration:`kb_admin_api` execute sync 端点改为入队返回 job id(不再请求线程内跑完整 ingest);dry-run 仍同步出 plan → 红
- [ ] 3.2 [实现] `kb_admin_api` sync/导入端点:execute 改入队;dry-run 保持同步;admin sync = 入队+等完成
- [ ] 3.3 [实现] cron / webhook 触发改为入队
- [ ] 3.4 [验证] 端点测试 + 脱敏断言(输出无 secret/全文)→ 绿

## 4. 过渡消费(worker 落地前不回退)

- [ ] 4.1 [实现] 最小过渡 drain:admin sync 入队后同进程内联消费这一条 job 并等完成;cron/webhook 入队后由同一过渡处理。**注释标注:`kb-worker` change 落地后移除**
- [ ] 4.2 [验证] integration:端到端 sync 一个本地目录,文档/chunk 经队列落 KB(与改造前结果一致)→ 绿

## 5. 收尾验证

- [ ] 5.1 [验证] `make test-pr` 全绿;`uv run pytest tests/integration -q` 对照 main 无新增失败
- [ ] 5.2 [验证] `make test-unit-ci` 覆盖率 ≥ 76%
- [ ] 5.3 [验证] `uv run alembic upgrade head` 后 `uv run alembic heads` 单一 head
- [ ] 5.4 [验证] `test_module_dependency_guardrails` 仍绿(队列经 db.py、不引入 ingest→platform 反向 import)
