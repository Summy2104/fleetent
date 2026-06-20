## ADDED Requirements

### Requirement: `fleetent chat` 子命令

`fleetent` 命令 SHALL 提供 `chat` 子命令,作为终端交互客户端的**唯一**入口。`fleetent chat [--url <ws>] [--token <key>]` SHALL 连接 `/ws` 做多轮对话(含斜杠命令),行为等价于改名前的 `fleetent tui` / 更早的 `fleetent-tui`。其 import SHALL 懒加载,不在 `fleetent agent run` 启动路径触发。

#### Scenario: chat 子命令连接 /ws

- **WHEN** 用户运行 `fleetent chat --url ws://localhost:8765/ws --token ma-<key>`
- **THEN** 客户端连接该 `/ws` 并进入多轮对话

#### Scenario: chat help 显示正确 prog 名

- **WHEN** 用户运行 `fleetent chat --help`
- **THEN** usage 行显示 `fleetent chat`

#### Scenario: chat 沿用 env 默认

- **WHEN** 设置 `FLEETENT_TUI_URL` / `FLEETENT_TOKEN` 后运行 `fleetent chat`
- **THEN** 子命令读取这些环境变量作为 `--url` / `--token` 默认值

#### Scenario: 旧 tui 子命令不再存在

- **WHEN** 用户运行 `fleetent tui`
- **THEN** 不被识别为 TUI 客户端入口(命令已改名为 `fleetent chat`)

## REMOVED Requirements

### Requirement: `fleetent tui` 子命令
**Reason**: 子命令名改为更直观、且为未来终端渠道双形态统一入口预留的 `chat`。
**Migration**: 用 `fleetent chat [--url <ws>] [--token <key>]` 替代 `fleetent tui`,行为不变。

#### Scenario: tui 子命令连接 /ws
- **WHEN** 用户运行 `fleetent tui --url ws://localhost:8765/ws --token ma-<key>`
- **THEN** 客户端连接该 `/ws` 并进入多轮对话,行为与原 `fleetent-tui` 相同

#### Scenario: 旧 fleetent-tui 入口不再存在
- **WHEN** 查看 `pyproject.toml` 的 `[project.scripts]`
- **THEN** 不含 `fleetent-tui` 入口;终端 TUI 仅经 `fleetent tui` 子命令暴露

#### Scenario: tui 沿用 env 默认
- **WHEN** 设置 `FLEETENT_TUI_URL` / `FLEETENT_TOKEN` 后运行 `fleetent tui`
- **THEN** 子命令读取这些环境变量作为 `--url` / `--token` 默认值
