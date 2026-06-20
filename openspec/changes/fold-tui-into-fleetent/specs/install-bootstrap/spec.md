## MODIFIED Requirements

### Requirement: Global command installation
install script SHALL 用 `uv tool install` 把 `fleetent` 安装为可在任意目录调用的全局命令。`fleetent-admin` / `fleetent-node` / `fleetent-tui` 不再作为独立 console script 安装——admin CLI 经 `fleetent admin` 子命令、node supervisor 经 `fleetent node start`、终端 TUI 经 `fleetent tui` 子命令调用。

#### Scenario: Entry point available globally
- **WHEN** 安装完成
- **THEN** `fleetent` console-script 入口链接到 `~/.local/bin`
- **AND** 在仓库目录之外也可调用
- **AND** 不存在独立的 `fleetent-admin` / `fleetent-node` / `fleetent-tui` 入口

#### Scenario: PATH hint when bin dir not on PATH
- **WHEN** `~/.local/bin` 不在用户 `PATH` 中
- **THEN** script 提示如何将其加入 PATH（或调用 uv 的 shell 更新）
- **AND** 不静默成功

#### Scenario: Install failure reports recovery hint
- **WHEN** `uv tool install` 未生成预期入口
- **THEN** script 告警并打印可手动复现的命令
- **AND** 以非零退出码退出
