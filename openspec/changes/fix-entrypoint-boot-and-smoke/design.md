## Context

两个主入口实测崩溃(见 proposal),根因是真实入口零 e2e 覆盖——单测 mock `run`、集成用 TestClient+fixture(fixture 会 set_state_db,掩盖平台裸启动崩溃)。本 change 修两个 bug + 立真实入口冒烟防线。

## Goals / Non-Goals

**Goals:** 平台 `uvicorn` 裸启动成功;一次性 `fleetent "<prompt>"` 真实跑通;补 subprocess/真实路径冒烟使"绿即可跑"。

**Non-Goals:** 不改 run()/run_stream 签名(改的是一次性调用方);不改 approval reconcile 逻辑(只挪进程);不补全量 e2e(只立入口冒烟最小集)。

## Decisions

### D1:一次性入口改用 Principal(不改 run 签名)

`run()` 与 `run_stream()` 已统一收 `principal: Principal | None`;`normalizer.py` 用 `Principal(user_id=msg.user_id, tenant_id="default")`。一次性 `_run` 是唯一漏改的——改为 `principal=Principal(user_id=user_id, tenant_id="default")`(import Principal)。不动 run() 签名,避免波及其它调用方。`user_id` 为 None 时按现有 Principal 语义处理(沿用 normalizer 的 default tenant)。

### D2:reconcile 归位到 agent boot

`reconcile_expired_approvals` 读 per-agent `approval_store`(agent 侧 state_db)。**平台进程没有也不该有单一 agent state_db**,所以这行在平台 lifespan 是放错位置的遗留。移除平台调用;加到 `agent_app` 的**异步 boot**(`_init_agent_db_schema` 已 `approval_store.set_state_db(agent_state_db)` 之后)——每个 agent 启动时清自己的过期审批(state_db 已接、async 上下文已有)。语义不变、归属正确;平台不再因此崩。

### D3:冒烟必须执行真实入口路径(不 mock 掉被测对象)

这是系统性修法的核心——冒烟若 mock 掉入口本身就白搭(正是现状)。
- **平台裸启动冒烟(e2e)**:`subprocess` 起 `uv run python -m uvicorn fleetent.server:app --port <p>`(注意:`uv run uvicorn` 实测会解析到系统 uvicorn,必须 `python -m uvicorn`),轮询 `/health` 200;超时/进程退出即 fail。真实复现裸启动 → 捕获 lifespan 崩溃。**不用 TestClient**(它 + fixture 会掩盖)。
- **agent serve 冒烟(e2e)**:`subprocess` 起 `fleetent agent run <临时 home id> --port <p>`,轮询 `/health`(或 `/chat` 存在)→ 可达即过。
- **一次性真实 run() 冒烟(integration)**:调 `run_sync`,在 **`get_client_and_config` 边界**打桩 LLM(返回最小 assistant 回复),**不 mock `loop.run`**——使 `_run → run()` 真实执行,捕获 principal/签名类不匹配。

### D4:e2e 入门禁口径

e2e 默认不进 PR 门禁(项目惯例)。但这几个入口冒烟价值高——design 建议:平台/agent 裸启冒烟可设计为**快**(只验启动+health,不真对话,秒级),纳入一个能在 PR/合并时跑的轻量集(或至少 daily)。具体纳入口径 apply 时按项目 CI 结构定;最低要求:这些冒烟存在且本地/CI 可一键跑。

## Risks / Trade-offs

- **[subprocess 冒烟的环境依赖]** 需 `python -m uvicorn`(非系统 uvicorn)、端口可用、超时控制。冒烟要稳:随机高端口 + 轮询超时 + 退出码检查 + teardown kill。
- **[一次性 user_id=None]** 若一次性入口 user_id 可空,Principal(user_id=None) 的下游语义需验(沿用 normalizer default-tenant 行为);测试覆盖 None 与具体 user_id 两情形。
- **[reconcile 移位影响]** 平台不再 reconcile = 正确(它本就不该);确认无别处依赖"平台启动时清审批"(已查:reconcile 唯一调用方就是平台 lifespan,agent_app 未调——移位后由 agent 承担,语义更对)。
