## 前置条件

**`kb-ingest-queue` 已落地 main**(队列表 + 入队 + claim/done/retry + 过渡 drain)。apply 前确认。

## 1. `fleetent kb-worker` 子命令

- [x] 1.1 [测试] `tests/unit/test_main_subcommands.py`:`test_kb_worker_subcommand_dispatches`(argv=["kb-worker"] 懒加载并进消费循环入口,mock 掉实际循环)+ `test_agent_run_does_not_import_kb_worker`(agent run 不 import worker 模块)→ 红
- [x] 1.2 [实现] `__main__.py` 加 `kb-worker` 分支懒加载 worker 入口
- [x] 1.3 [验证] `uv run pytest tests/unit/test_main_subcommands.py -x -q` → 绿

## 2. worker 消费循环(唯一消费者 / 单一写入方)

- [x] 2.1 [测试] integration `tests/integration/test_kb_worker.py`:入队一条 job → 跑 worker 一轮 → job done 且 KB 写入;失败 job → retry 到上限置 failed → 红
- [x] 2.2 [实现] worker 循环:原子 claim → 调 `knowledge_base.ingest` 核 → mark done/failed(retry);经 `db.py`,不 import platform
- [x] 2.3 [验证] `uv run pytest tests/integration/test_kb_worker.py -x -q` → 绿

## 3. 移除过渡 drain + admin sync 改轮询

- [x] 3.1 [测试] integration:admin sync(execute)入队后经轮询 job 状态返回结果;断言**无**过渡内联 drain 路径 → 红
- [x] 3.2 [实现] 删除 `kb-ingest-queue` 的过渡内联 drain;admin sync 改"入队 + 轮询 job 状态(超时返回 job id + 状态)"
- [x] 3.3 [验证] `git grep` 确认无残留过渡 drain;端到端 sync 经 worker 完成 → 绿

## 4. 收尾验证

- [x] 4.1 [验证] `make test-pr` 全绿;`uv run pytest tests/integration -q` 无新增失败
- [x] 4.2 [验证] `make test-unit-ci` 覆盖率 ≥ 76%
- [x] 4.3 [验证] `test_module_dependency_guardrails` 绿:`knowledge_base`(含 worker 入口)MUST NOT import platform;`fleetent agent run` 不加载 worker
- [x] 4.4 [验证] 生产无绕过队列/worker 的 ingest 路径(`git grep` 直接调核仅在 tests/)
