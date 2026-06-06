## Why

近期配置布局连续调整后，代码、文档和 OpenSpec 中仍残留多套旧语义：

- `config/` 仍被部分 spec / docs / loader 描述为配置或模板入口。
- `agent-runtime-cli` 与部分平台 deploy 逻辑仍提到 `FLEETENT_HOME/<id>/agent.yaml`，但当前目标布局是
  `FLEETENT_HOME/agents/<id>/agent.yaml`。
- `agents/default/` 下新增了多个相似 example 文件，容易让 operator 和后续实现者误判哪个才是
  canonical runtime template。
- MCP 仍保留 `config/mcp.servers.yaml` 默认文件语义，与 Platform DB + Agent materialize 的方向冲突。

MVP 尚未上线，本 change 不做向后兼容。目标是把 Platform / Agent 配置契约一次性钉死，并用测试防止后续改动回退到旧路径。

## What Changes

- 删除 `config/` 作为 runtime config、template、legacy fallback 的任何当前语义。
- 仓库 canonical 配置模板只保留：
  - `.env.example`
  - `platform.yaml.example`
  - `agents/default/agent.yaml.example`
  - `agents/default/.env.example`
- 这 4 个 example SHALL be complete reference examples:
  - `platform.yaml.example` 覆盖当前 Platform 非敏感配置字段与 embedded Platform capability 配置段。
  - `.env.example` 覆盖 `platform.yaml.example` 与 Platform process 所引用的 env key。
  - `agents/default/agent.yaml.example` 覆盖当前 `AgentFile` schema 支持的字段与主流 protocol/route 示例。
  - `agents/default/.env.example` 覆盖 `agents/default/agent.yaml.example` 中所有 `*_env` / env 引用 key。
- 删除 `agents/default/.env.standalone.example`、`agent.configure.yaml.example`、
  `agent.defaults.yaml.example` 等非 canonical 模板；字段解释进入 docs / specs。
- Agent home 统一为 `agents/<agent-id>/`：
  - `agents/<agent-id>/agent.yaml`
  - `agents/<agent-id>/.env`
  - `agents/<agent-id>/data/`
- `fleetent agent run/init/restart <id>`、Platform materialize、admin deploy 全部使用
  `FLEETENT_HOME/agents/<id>/`。
- 移除默认 `config/mcp.servers.yaml` loader 和文档语义。MCP 定义来自 Platform DB authoring；
  Agent 绑定后 materialize 到 `agent.yaml`。
- 明确 Platform process env 来源为 Platform home `.env`，外部环境变量优先；Agent process env 来源为
  Agent home `.env`，外部环境变量优先。
- 增加 repo/docs/spec guard tests，禁止旧路径和旧模板重新出现。

## Non-Goals

- 不提供旧 `config/` 布局迁移脚本。
- 不保留 `FLEETENT_HOME/agent.yaml`、`FLEETENT_HOME/<id>/agent.yaml`、
  `config/agents/<id>/agent.yaml` fallback。
- 不新增 standalone Knowledge Service 配置契约。
- 不改变 Model / KB / MCP 的业务数据模型，除非它们当前仍依赖旧文件路径。

## Capabilities

### Modified Capabilities

- `configuration`: canonical templates and runtime config exclude `config/`; only root Platform files
  and `agents/default` examples remain.
- `runtime-paths`: `config_dir()` is no longer a current deployment contract; Platform home and Agent
  home accessors own the supported paths.
- `agent-runtime-cli`: standalone agent commands resolve to `agents/<id>/`.
- `platform-agent-lifecycle`: materialize/deploy writes only `agents/<id>/`.
- `mcp-client`: startup/global MCP definitions no longer come from `config/mcp.servers.yaml`.
