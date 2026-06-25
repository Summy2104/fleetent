## MODIFIED Requirements

### Requirement: Platform CLI namespace

系统 SHALL 提供 `fleetent platform` 作为 Platform/control-plane 的唯一本地 CLI
namespace。所有控制面 bootstrap、配置校验、基础设施供给、diagnostics 与危险维护命令
SHALL 位于该 namespace 下。系统 SHALL NOT 提供 `fleetent admin` 兼容 alias。

`admin` 一词仍可作为权限角色、built-in admin 用户和 HTTP `/admin/*` 路径语义存在；本
requirement 只约束 `fleetent` CLI namespace。

`fleetent platform init-config` SHALL 接受 `--home <path>` 参数；未传入时默认用 `paths.base_dir()`（受 `FLEETENT_HOME` 控制），不再隐含 `cwd`。

#### Scenario: Platform CLI dispatches

- **WHEN** operator 运行 `fleetent platform validate-config --format json`
- **THEN** CLI 调度到 Platform CLI，并以 `prog="fleetent platform"` 渲染 help/error

#### Scenario: Admin CLI namespace removed

- **WHEN** operator 运行 `fleetent admin validate-config`
- **THEN** CLI 不调度 Platform CLI
- **AND** 命令以未知 top-level command 失败

#### Scenario: Agent runtime does not import Platform CLI

- **WHEN** 调度到 `fleetent agent run`
- **THEN** Platform CLI 实现模块未被 import

#### Scenario: init-config 使用 --home 而非 cwd

- **WHEN** operator 在任意目录运行 `fleetent platform init-config --home /opt/fleetent`
- **THEN** `.env` 和 `platform.yaml` 在 `/opt/fleetent/` 下创建，当前工作目录不影响结果
