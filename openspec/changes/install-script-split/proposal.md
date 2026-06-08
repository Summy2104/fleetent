## Why

`scripts/install.sh` 是一个"大杂烩"脚本，将 standalone agent 部署和 platform 控制面
部署的逻辑混在一起：agent 侧只需要安装 fleetent binary + `fleetent agent init`，
platform 侧需要 alembic 建表和 admin 用户初始化。混合脚本对部署测试服务器时造成不必要的
依赖（alembic、`fleetent-admin`），也与 agent⊥platform 解耦原则相悖。

经过三项前置改动（per-agent-data-isolation、agent-db-schema-init、tui-agent-auth），
standalone agent 已完全不需要 alembic，且 TUI 认证也不再依赖 platform user_store，
现在是拆分安装脚本的最佳时机。

## What Changes

- **新建** `scripts/install-agent.sh`：部署一个 standalone agent 进程
  - 安装 uv（若无）
  - 检查 Python 3.12+
  - `uv tool install --from . fleetent`（生产模式，不需要源码永久存在）
  - 持久化 `FLEETENT_HOME` 到 shell rc
  - `fleetent agent init <agent-id>`（必须作为参数传入）
  - 检查 Docker（可选，sandbox 用）
  - 不运行 alembic，不需要 `fleetent-admin`
- **新建** `scripts/install-platform.sh`：部署 platform 控制面
  - 安装 uv + Python 3.12+
  - `uv tool install --from . fleetent`
  - 持久化 `FLEETENT_HOME`
  - 复制 `.env.example` → `.env`，`platform.yaml.example` → `platform.yaml`
  - `alembic upgrade head`（仅 platform DB：`$FLEETENT_HOME/data/fleetent.db`）
  - `fleetent-admin seed-builtin-admin`（创建初始管理员）
- **重构** `scripts/install.sh`：开发者一键安装，调用前两者
  - 沿用 `--editable` 安装（开发态）
  - 接受 `--agent-only` / `--platform-only` / `--dir PATH` 参数
  - 默认：先 install-platform.sh 再 install-agent.sh default

## Capabilities

### New Capabilities

- `install-agent-script`: 专为 standalone agent 设计的安装脚本，无 alembic 依赖
- `install-platform-script`: 专为 platform 控制面设计的安装脚本

### Modified Capabilities

- `deployment`: 安装脚本分为 agent / platform / 开发者三种路径

## Impact

- `scripts/install-agent.sh` — 新建
- `scripts/install-platform.sh` — 新建
- `scripts/install.sh` — 重构为调用子脚本的组合器
- `docs/local/my-bot-deployment.md` — 更新安装命令（不跟踪 git）
