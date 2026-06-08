## Context

`scripts/install.sh` 现状：
- `ensure_uv`：安装 uv（agent + platform 都需要）
- `check_python`：检查 Python 3.12+（都需要）
- `install_tool`：`uv tool install --force --editable`（只适合开发者）
- `setup_home_env`：持久化 FLEETENT_HOME（都需要）
- `copy_config_templates`：复制 agent.yaml.example + platform.yaml.example + .env.example
  - 其中 `agents/default/.env.example` 不存在（dead code）
  - agent 部分应改为调用 `fleetent agent init <id>`
- `init_db`：`alembic upgrade head` 建全部表（agent-side + platform-side）
  - 经 agent-db-schema-init，agent 侧表已由 store 自建，alembic 只需建 platform 表
- `precheck_docker`：可选，与 agent 相关

前置 change 落地后，agent 安装路径极简：装 binary + init agent。

## Goals / Non-Goals

**Goals**
- `install-agent.sh <agent-id>`：无 alembic，无 fleetent-admin，standalone 完整可运行
- `install-platform.sh`：alembic 只运行 platform DB（migrations 001-002 之类的平台表）
- `install.sh`：开发者一键安装，调用前两者，保留 `--editable` 模式

**Non-Goals**
- Docker Compose 生产部署路径（另行维护）
- Windows/WSL2 以外的 Windows 原生支持

## Decisions

**D1 — `install-agent.sh` 必须传 agent-id**

```bash
scripts/install-agent.sh my-bot
```

无默认值，强制明确，避免歧义。若未传则打印 usage 并退出。

**D2 — `install-agent.sh` 用 `--from .`，`install.sh` 用 `--editable`**

`--from .` 不要求源码目录永久存在，适合生产服务器；
`--editable` 开发者 in-place 改动立即生效，适合本地开发。

**D3 — `install-platform.sh` 的 alembic 只建 platform 表**

agent-db-schema-init 已确认 agent-side 表（migrations 003-009）由 store 自建。
`install-platform.sh` 只需要建 platform 表（001-002：users/im_users/agents 等）。
但为简化维护，仍运行 `alembic upgrade head`（幂等；多建几张 agent-side 表也无害，
因为独立 DB 文件不影响 agent-side store 的自建逻辑）。

**D4 — `install.sh` 改为调用子脚本**

```bash
install.sh
  ├── 公共步骤：ensure_uv, check_python
  ├── install_platform 函数：调用 install-platform.sh
  └── install_agent 函数：调用 install-agent.sh default
```

接受 `--agent-only` / `--platform-only` / `--agent-id <id>` 参数。

## Risks / Trade-offs

- **已有 install.sh 用户**：行为变化（调用子脚本），但参数接口兼容。
  Mitigation：保留同名，默认行为相同（全装）。
- **alembic 在 install-platform.sh 中仍运行 upgrade head**：
  当前 9 个 migrations 包含 agent-side 表，这意味着 platform DB 也会建 agent-side 表。
  这是暂时的技术债；长期可将 migrations 分拆为 platform/agent 两套。
  不在本 change 解决。
