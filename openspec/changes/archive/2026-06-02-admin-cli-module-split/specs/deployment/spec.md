## ADDED Requirements

### Requirement: Fleetent admin command compatibility
部署 SHALL 继续提供 `fleetent-admin` 作为管理员和 operator 的本机 CLI 入口。

#### Scenario: Fleetent admin command remains available
- **WHEN** operator 按部署文档运行 `uv run fleetent admin`
- **THEN** CLI 使用新的 `platform.admin_cli` 实现
- **AND** 对 operator 暴露的命令名、参数和输出保持兼容
