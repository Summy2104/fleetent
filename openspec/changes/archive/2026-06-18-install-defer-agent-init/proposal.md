## Why

安装脚本当前把"装运行时"和"创建某个 agent"耦合在一起：`install-agent.sh <agent-id>` 必须带 agent-id 并直接跑 `fleetent agent init`，`install.sh` 也自动 seed 一个 `agents/default/` home。这有两个问题：① 安装（机器级、一次性、幂等）和 agent 创建（按需、用户自定 id/配置、可建多个）被绑死，用户想自己命名/多建 agent 时反而要先删掉默认产物；② agent 创建被脚本"代办"，用户对 `fleetent agent init` 这一步无感知。把 agent 初始化从安装脚本剥离、改为脚本结尾打印教程引导用户自己执行，更符合"装一次、按需建 agent"的心智。

## What Changes

- `scripts/install-agent.sh`：**去掉必填的 `<agent-id>` 位置参数**（签名变为 `install-agent.sh [--dir PATH]`）；**移除 `fleetent agent init` 步骤**；结尾改为打印"如何创建并运行 agent"的教程。脚本只做：装 `fleetent` binary、设并持久化 `FLEETENT_HOME`、环境探测（Python≥3.12、Docker 可选告警），幂等可重入。
- `scripts/install.sh`（开发者一键、editable）：**不再自动 seed 默认 agent home**；agent 分支收敛为"装运行时 + 设 home + 打印教程"，移除 `--agent-id`。platform 分支不变（仍 editable 装 + alembic 建库）。
- 两脚本结尾的教程文本统一为四步：`fleetent agent init <agent-id>` → 编辑 `agent.yaml` + `.env`（`chmod 600 .env`）→ `fleetent agent run <agent-id> [--port N]` → `fleetent-tui` 连接。
- `scripts/install-platform.sh` **不改**（继续 seed platform home + alembic + seed admin）。
- **BREAKING（部署脚本接口）**：`install-agent.sh <agent-id>` 的旧用法变更——agent-id 不再被脚本消费；安装后用户须自行 `fleetent agent init <id>`。帮助文本说明。
- **脚本不改名**（沿用 `install-agent.sh`）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `install-agent-script`: `install-agent.sh` 改为只装 binary + 设 `FLEETENT_HOME` + 打印创建 agent 的教程；不再跑 `fleetent agent init`、不再产出 runnable agent home、不再要求 `agent-id`（无位置参数，仅 `--dir`）；保持无 platform/alembic 依赖与幂等。
- `install-bootstrap`: 一键 `install.sh` 不再 seed 默认 Agent home（`agents/default/`），改为打印创建 agent 教程；继续 seed Platform home + 初始化 DB；"Platform home 不得同时当 Agent home" 的约束保留。

## Impact

- 文件：`scripts/install-agent.sh`（删 agent-id 与 init、改帮助+教程）、`scripts/install.sh`（删 `--agent-id` 与默认 agent seed、改教程）。
- public API surface：`install-agent.sh` 命令行接口（移除 agent-id 位置参数）、两脚本结尾教程输出。
- owned tables：无；config namespace：无；src 代码：无改动。
- cross-module dependencies：无（纯部署脚本 + spec）。
- migration / shim：无代码 shim；旧 `install-agent.sh <agent-id>` 调用的多余位置参数在帮助文本中说明已移除。
- 测试：`install-agent-script` / `install-bootstrap` 的相关 integration/doc 测试需同步（断言不再产出默认 agent home、不再要求 agent-id、教程文本存在）。
- `install-platform.sh` 及平台安装链路不受影响。
