## MODIFIED Requirements

### Requirement: Standalone agent runtime via `fleetent agent run`

`fleetent agent run <agent-id> [--port N]` SHALL boot a single agent home as a foreground process (loop + bound IM + optional HTTP/ws): 解析 `FLEETENT_HOME/agents/<agent-id>/` 的 agent home（`agent.yaml` + `.env` + `data/`），加载并运行 agent loop、启动其 IM 连接。**该命令是 node 拉起 agent 的原语**（node 经 subprocess 调用它）**, 也可被开发者直接运行作 dev/test 调试**。

该命令在运行时 **MUST NOT** 依赖 platform（agent→platform 解耦契约;agent 运行时不调 platform）。但"无 platform 的 standalone 部署"**不再是受支持的部署模式**——生产部署 platform 始终在场,agent 由 node 拉起、配置由 platform materialize 下发（见 `deployment`）。`fleetent agent run` 直接手跑仅用于 dev/test,不作部署形态。

Before scanning `agent.yaml`, `boot()` SHALL load `<home_dir>/.env` into the process `os.environ` using `load_dotenv(override=False)`; 文件不存在则静默跳过;进程环境（systemd / Docker / node 注入）优先。

#### Scenario: node 经 agent run 拉起 agent
- **WHEN** node reconcile 时对某 agent 调 `fleetent agent run <id> --home <materialized-home>`
- **THEN** 该进程加载 materialized home 并运行,无需在该进程内 import 或调用 platform

#### Scenario: dev 直接跑 agent run 调试
- **WHEN** 开发者本地 `fleetent agent run support` 调试
- **THEN** 进程加载该 home 并运行;这是 dev/test 用法,不是受支持的 standalone 部署

#### Scenario: .env 在扫描 agent.yaml 前加载
- **WHEN** `<home_dir>/.env` 存在且含 `SLACK_BOT_TOKEN=xoxb-abc`
- **THEN** 该值在 `boot()` 扫描 agent.yaml 前进入 `os.environ`（进程已有同名值优先）
