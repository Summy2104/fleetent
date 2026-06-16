## MODIFIED Requirements

### Requirement: Global command installation
install script SHALL 用 `uv tool install` 把 `fleetent`、`fleetent-admin` 安装为可在任意目录调用的全局命令。`fleetent-tui` console-script 入口已随终端 TUI 客户端移除，不再安装。

#### Scenario: Entry points available globally
- **WHEN** 安装完成
- **THEN** `fleetent`、`fleetent-admin` 两个 console-script 入口链接到 `~/.local/bin`
- **AND** 在仓库目录之外也可调用
- **AND** 不再链接 `fleetent-tui`

#### Scenario: PATH hint when bin dir not on PATH
- **WHEN** `~/.local/bin` 不在用户 `PATH` 中
- **THEN** script 提示如何将其加入 PATH（或调用 uv 的 shell 更新）
- **AND** 不静默成功

#### Scenario: Install failure reports recovery hint
- **WHEN** `uv tool install` 未生成预期入口
- **THEN** script 告警并打印可手动复现的命令
- **AND** 以非零退出码退出
