## Why

`agent.yaml` 的 `observability.logging.directory` 配置为相对路径（如 `data/logs`）时，按进程 CWD 解析，日志文件随启动位置漂移。实际案例（2026-06-10）：my-bot 配置 `directory: data/logs`，在仓库目录启动后日志落到仓库 `data/logs/` 而非 agent 家目录 `~/.fleetent/agents/my-bot/data/logs/`——用户在 agent 家目录下找不到日志。配置文件中的相对路径应相对 agent 家目录解析，与留空时的默认行为（`home/data/logs`）一致。

## What Changes

- `runtime/agent_app.py:_configure_logging_from_agent` 解析 `observability.logging.directory` 时：
  - **相对路径** → 拼接 agent 家目录解析（`home_dir / directory`），不再随 CWD 漂移
  - **绝对路径** → 保持原样（显式指定全局位置仍可用）
  - **留空** → 默认 `home_dir / "data" / "logs"`（现有行为不变）
- 范围仅 standalone agent runtime 路径；platform 服务（`server.py` 经 `configure_logging(Settings)`）不动

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `agent-log-format-wiring`: `directory` 字段不再"原样透传"——相对路径 SHALL 相对 agent home 解析后再传给 `configure_structured_logging`；绝对路径与留空行为不变

## Impact

- **代码**：`src/fleetent/runtime/agent_app.py`（`_configure_logging_from_agent` 单点修改）
- **测试**：`tests/unit/` 下 agent_app 日志配置相关测试（相对/绝对/留空三态）
- **行为变更**：已有部署若依赖"相对路径按 CWD 解析"的旧行为（无已知案例，该行为本身即缺陷），日志位置将迁移到 agent 家目录下
- **不影响**：platform server 日志路径、`structured_logging.py` 本体、agent.yaml schema（字段含义更直觉，无格式变化）
