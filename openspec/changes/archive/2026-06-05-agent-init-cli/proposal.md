## Why

`fleetent agent run <agent-id>` 跑 `FLEETENT_HOME/<agent-id>/agent.yaml`，但**没有对应的命令去 scaffold 出那个 home**——只有平台侧 `materialize`（DB→home，需控制面/HTTP）。在不起平台、纯运行时/dev 场景下，要新建一个可跑的 agent 必须手抠目录与 `agent.yaml`、且 `name` 字段必须等于目录名（否则 `agent run` 校验失败，易踩坑）。本 change 加 `fleetent agent init <agent-id>`：从**内置模板**零平台依赖地 scaffold 出一个可被 `fleetent agent run` 直接跑的 home。

## What Changes

- 新增 CLI 子命令 `fleetent agent init <agent-id> [--home PATH] [--force]`：
  - home = `--home` 或 `FLEETENT_HOME/<agent-id>`（复用 `agent_app.resolve_home`）
  - 写 `home/agent.yaml`——从**代码内置模板**生成，`name` 强制设为 `<agent-id>`（满足 `agent run` 的目录名==name 校验）；核心字段（system_prompt/model_overrides/skills/allowed_tools/plugins/features/mcp_servers/connectors/bindings），不含 KB/intelligence
  - 写 `home/.env`——**列出模板引用的 env-var 名**（空值待填，如 `ANTHROPIC_API_KEY=`），存在即跳过
  - 已存在 `agent.yaml` 且无 `--force` → 报错非零退出；`--force` 覆盖 agent.yaml（仍不覆盖已有 `.env`）
- 新增 `runtime/agent_init.py`（单一职责：scaffold）；`__main__.py` 加 `agent init` 分支（现仅 `agent run`）。

## Capabilities

### Modified Capabilities
- `agent-runtime-cli`: 新增「`fleetent agent init` scaffold 一个 agent home」要求——从内置模板生成可被 `agent run` 直接运行的自包含 home（`name`==目录名、`.env` 列出引用的 env 名），零平台/DB 依赖。

## Impact

- **新增**：`src/fleetent/runtime/agent_init.py`、`tests/unit/test_agent_init.py`。
- **修改**：`src/fleetent/__main__.py`（加 `agent init` 分支 + 用法）。
- **不依赖**：platform / DB（纯本地）；复用 `agent_app.resolve_home`、`agent_config.AgentFile`(校验生成内容)。
- **不受影响**：平台 `materialize`（DB→home）、`agent run`、install.sh（仍 seed 单 home agent 的 `config/agent.yaml`）。
- **分支**：基于并合回 `main`。
