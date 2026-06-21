## MODIFIED Requirements

### Requirement: install-agent.sh deploys a standalone agent without platform dependencies

`scripts/install-agent.sh [--dir PATH]` SHALL install the fleetent runtime **and node supervisor** on an **agent host**, set and persist `FLEETENT_HOME`, run the optional-dependency precheck (warn when Docker is absent), and then print a tutorial guiding the operator to **配置 node 接入 platform**(写 `$FLEETENT_HOME/node/.env`:platform 基址 / node-id / service key)并以 `fleetent node start` 启动。脚本 SHALL NOT 把"无 platform 的 standalone agent"作为部署形态引导(standalone 部署已退役)。它 SHALL NOT run `fleetent agent init`、SHALL NOT produce an agent home、SHALL NOT 要求 agent-id 参数、SHALL NOT run alembic migrations。脚本 SHALL idempotent / re-runnable。`fleetent agent init` / `agent run` 在教程里 SHALL 仅作 **dev/test 调试**用法提及,不作部署步骤。

#### Scenario: install 装 runtime+node 并引导接入 platform
- **WHEN** `scripts/install-agent.sh` 在 fleetent 仓目录被调用(无位置参数)
- **THEN** `fleetent` 运行时 + node 被安装、`FLEETENT_HOME` 设置/持久化
- **AND** 脚本零退出并打印教程:配置 `$FLEETENT_HOME/node/.env`(platform 基址/node-id/service key)→ `fleetent node start` 接入 platform
- **AND** 不创建任何 agent home、不跑 alembic

#### Scenario: 位置参数 agent-id 被拒
- **WHEN** `scripts/install-agent.sh some-id` 带位置参数
- **THEN** 脚本非零退出并提示该参数已移除

#### Scenario: 教程把 agent run 标为 dev 用法、部署走 node
- **WHEN** install 完成打印教程
- **THEN** 部署路径是"配 node → `fleetent node start`";`fleetent agent init`/`agent run` 仅作 dev/test 调试提及,不作部署步骤
