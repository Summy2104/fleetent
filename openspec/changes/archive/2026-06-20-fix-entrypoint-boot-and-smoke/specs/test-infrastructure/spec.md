## ADDED Requirements

### Requirement: 真实入口冒烟,不 mock 掉被测入口

系统 SHALL 有冒烟测试**执行真实入口路径**,使"测试绿"蕴含"入口能启动",而非被 mock/fixture 掩盖。冒烟 SHALL NOT mock 掉被测的入口本身(如 mock `loop.run` 来测一次性、用预先 `set_state_db` 的 fixture 掩盖平台裸启动)。

至少覆盖:
- **平台裸启动**:以 subprocess 真起 `python -m uvicorn fleetent.server:app`(非系统 `uvicorn`),轮询 `/health` 返回 200;进程退出/超时即 fail。
- **agent serve**:以 subprocess 真起 `fleetent agent run <id> --port`,`/health`(或 `/chat`)可达。
- **一次性 run()**:`run_sync` 在 `get_client_and_config` 边界打桩 LLM,`_run → run()` 真实执行(见 agent-runtime-cli)。

#### Scenario: 平台裸启动冒烟捕获 boot 崩溃

- **WHEN** 平台裸启动冒烟运行(subprocess uvicorn + /health 轮询)
- **THEN** 平台无法启动(如 lifespan 崩)时冒烟 fail,而非被 TestClient+fixture 掩盖

#### Scenario: 冒烟用 subprocess 而非 TestClient 测裸启动

- **WHEN** 验证平台/agent 的真实启动
- **THEN** 经 subprocess 起真实进程 + HTTP 探活,不靠 TestClient(后者会掩盖裸启动路径的 wiring 缺失)

#### Scenario: 一次性冒烟不 mock run 本身

- **WHEN** 一次性入口冒烟运行
- **THEN** 它只在 LLM 边界(`get_client_and_config`)打桩,真实执行 `run()`;入口与 run 签名不匹配 SHALL 被捕获
