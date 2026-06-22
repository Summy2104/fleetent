## Why

实测发现:**两个主入口都无法启动**,而 5248 个测试全绿——测试 mock 掉 LLM/run、用 TestClient + fixture,从不真正执行真实入口路径,所以入口腐烂无人知。

1. **平台 `uvicorn fleetent.server:app` 启动崩溃**:lifespan 调 `reconcile_expired_approvals()`(agent 侧操作,读 per-agent state_db),但平台进程从不 `set_state_db` → `RuntimeError: approval_store: state_db not initialized`。approval 解耦后是 agent 侧数据,平台没有单一 agent state_db 可 reconcile——这行是解耦遗留、放错了进程。
2. **一次性 `fleetent "<prompt>"` TypeError**:`loop._run` 调 `run(..., user_id=user_id)`,但 `run()` 签名收的是 `principal`(自 2026-06-07 起 run_stream/normalizer 都用 principal,唯独一次性入口没跟上)→ `TypeError: run() got an unexpected keyword argument 'user_id'`。

两者均 pre-existing。本 change 修这两个入口,并**补真实入口冒烟**(系统性堵住"测试绿 ≠ 能跑")。

## What Changes

- **修一次性入口**:`runtime/loop.py` 的 `_run` 把 `user_id=user_id` 改为 `principal=Principal(user_id=user_id, tenant_id="default")`(对齐 `im_gateway/normalizer.py` 与 `run_stream` 的 principal 用法)。
- **修平台启动**:`reconcile_expired_approvals()` 从 `server.py` lifespan **移除**;加到 **agent_app 异步 boot**(`_init_agent_db_schema` 设 `set_state_db` 之后)——每个 agent 启动时清理自己的过期审批(state_db 已接、归属正确)。平台 lifespan 不再做这件 agent 侧的事。
- **补真实入口冒烟测试**(关键,系统性修法):
  - e2e:subprocess 真起 `uvicorn fleetent.server:app` → 轮询 `/health` 返回 200(faithful 复现裸启动,捕获 lifespan 崩溃)。
  - e2e:subprocess 真起 `fleetent agent run <id> --port` → `/health` / `/chat` 可达(agent serve 路径)。
  - integration:一次性 `run_sync` 在 **`get_client_and_config` 边界** mock LLM(而非 mock `run`),使 `_run → run()` 真实调用执行——捕获签名不匹配(现有 test_run_sync_home_agent mock 了 run、绕过了 bug)。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `agent-runtime-cli`:一次性入口经 `principal` 调 `run()`(修 TypeError);新增"真实入口冒烟"要求。
- `platform-control-plane`:平台启动 SHALL 不依赖 agent 侧 state_db(不在 lifespan 跑 agent 侧 approval reconcile);`uvicorn fleetent.server:app` SHALL 能裸启动。
- `test-infrastructure`:新增"真实入口冒烟覆盖"要求(裸启平台/agent serve/一次性真实 run()),堵住 mock 绕过入口腐烂。

## Impact

**owning package**:`runtime/loop.py`(principal)、`server.py`(移除 reconcile)、`runtime/agent_app.py`(加 reconcile)、`tests/e2e` + `tests/integration`(冒烟)

**public API surface**:无变更;修复入口可用性

**owned tables**:无　**config namespace**:无　**migration**:无

**cross-module dependencies**:无新增;reconcile 归位到 agent boot(state_db 已接处);Principal 已是 runtime 内类型

**根因/系统性**:真实入口零 e2e 覆盖。本 change 既修这两个 bug,也立"入口冒烟"这道防线——以后入口腐烂会被 CI 抓住,而非手动跑才发现。冒烟须**执行真实入口路径**(subprocess 裸启 / get_client_and_config 边界 mock),不得 mock 掉被测的入口本身。
