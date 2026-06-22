## ADDED Requirements

### Requirement: `fleetent tui` 子命令

`fleetent` 命令 SHALL 提供 `tui` 子命令,作为终端 TUI 客户端的**唯一**入口(独立 `fleetent-tui` console-script 已移除)。`fleetent tui [--url <ws>] [--token <key>]` SHALL 等价于原 `fleetent-tui` 的全部行为:连接 `/ws`、多轮对话、斜杠命令。其 import SHALL 懒加载,不在 `fleetent agent run` 启动路径触发。

#### Scenario: tui 子命令连接 /ws

- **WHEN** 用户运行 `fleetent tui --url ws://localhost:8765/ws --token ma-<key>`
- **THEN** 客户端连接该 `/ws` 并进入多轮对话,行为与原 `fleetent-tui` 相同

#### Scenario: 旧 fleetent-tui 入口不再存在

- **WHEN** 查看 `pyproject.toml` 的 `[project.scripts]`
- **THEN** 不含 `fleetent-tui` 入口;终端 TUI 仅经 `fleetent tui` 子命令暴露

#### Scenario: tui 沿用 env 默认

- **WHEN** 设置 `FLEETENT_TUI_URL` / `FLEETENT_TOKEN` 后运行 `fleetent tui`
- **THEN** 子命令读取这些环境变量作为 `--url` / `--token` 默认值
