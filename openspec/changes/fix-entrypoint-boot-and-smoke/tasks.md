## 1. 真实入口冒烟先行(先红:暴露当前两个 bug)

- [ ] 1.1 [测试] `tests/e2e/test_platform_boot_smoke.py`:subprocess 起 `uv run python -m uvicorn fleetent.server:app --port <随机高端口> --log-level warning`,轮询 `/health` 200(超时/进程退出即 fail);teardown kill。**当前应红**(lifespan `reconcile_expired_approvals` 崩)
- [ ] 1.2 [测试] `tests/integration/test_run_sync_real_run.py`:`run_sync`(或一次性入口)在 `get_client_and_config` 边界打桩 LLM、**不 mock `loop.run`**,断言返回回复无 TypeError。**当前应红**(`run() got unexpected kwarg user_id`)
- [ ] 1.3 [测试] `tests/e2e/test_agent_serve_smoke.py`:subprocess 起 `fleetent agent run <临时 home id> --port <随机端口>`(临时 FLEETENT_HOME),轮询 `/health`/`/chat` 可达;teardown
- [ ] 1.4 [验证] 跑 1.1/1.2 → 确认红(复现两个入口 bug)

## 2. 修一次性入口(Principal)

- [ ] 2.1 [实现] `runtime/loop.py` 的 `_run`:`user_id=user_id` → `principal=Principal(user_id=user_id, tenant_id="default")`(import Principal,对齐 normalizer/run_stream);不改 `run()`/`run_stream()` 签名
- [ ] 2.2 [验证] `uv run pytest tests/integration/test_run_sync_real_run.py -x -q` → 绿;手验 `uv run fleetent "What is 7*8?"` 真出话

## 3. 修平台启动(reconcile 归位 agent boot)

- [ ] 3.1 [实现] `server.py` lifespan:移除 `reconcile_expired_approvals()` 调用(及其 import)
- [ ] 3.2 [实现] `runtime/agent_app.py` 异步 boot:在 `_init_agent_db_schema`(已 `approval_store.set_state_db`)之后调 `reconcile_expired_approvals()`——agent 启动清自己的过期审批
- [ ] 3.3 [验证] `uv run pytest tests/e2e/test_platform_boot_smoke.py -x -q` → 绿;手验 `uv run python -m uvicorn fleetent.server:app` 起得来 + `/health` 200
- [ ] 3.4 [验证] agent boot 后过期审批被清(加/复用 integration 验证 reconcile 在 agent 侧真生效)

## 4. 收尾验证

- [ ] 4.1 [验证] 三个冒烟全绿(1.1/1.2/1.3)
- [ ] 4.2 [验证] `make test-pr` 全绿 + `make test-unit-ci` 覆盖率 ≥ 76%
- [ ] 4.3 [验证] **全量 integration**(本 change 动 server lifespan + loop + agent_app boot,属跨切面/启动路径)对照 main 基线无新增失败
- [ ] 4.4 [验证] `test_module_dependency_guardrails` 绿;reconcile 移位未引入 agent→platform 反向 import
- [ ] 4.5 [验证] 手验端到端:`uvicorn server` 起 + 注册 node + `agent run` 起 + 真实对话跑通一次(确认"整套机制能跑")
- [ ] 4.6 [验证] `openspec validate fix-entrypoint-boot-and-smoke`
