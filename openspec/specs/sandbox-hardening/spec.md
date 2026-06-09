# sandbox-hardening Specification

## Purpose
TBD - created by archiving change sandbox-hardening. Update Purpose after archive.
## Requirements
### Requirement: 容器 env 注入支持白名单

`build_sandbox_env` SHALL 支持可选的名字白名单：提供白名单时，仅白名单内的变量名可注入容器，且仍叠加既有 sensitive 名字黑名单（白名单内但 sensitive 的名字仍被剔除）。不提供白名单时保持既有行为。

#### Scenario: 白名单只放行声明的变量
- **WHEN** 以 `allowlist={"FOO"}` 调用 build_sandbox_env，输入含 FOO 与 BAR
- **THEN** 结果只含 FOO

#### Scenario: 白名单不豁免 sensitive 名字
- **WHEN** allowlist 含一个 sensitive 名字（如 `API_KEY`）
- **THEN** 该名字仍被黑名单剔除，不注入

### Requirement: workspace 挂载路径黑名单

派生用于 bind mount 的 workspace 宿主目录 SHALL 经路径黑名单校验：当其规范化路径等于或落在敏感宿主根（如 `~/.ssh`、`~/.aws`、`~/.gnupg`、`/etc`、`/root`）内时，MUST 拒绝（不返回路径、不创建容器/挂载）。

#### Scenario: 敏感根被拒绝
- **WHEN** workspace 目录解析后落在 `~/.ssh` 内
- **THEN** 拒绝并报错，不进行 bind mount

#### Scenario: 正常 workspace 目录放行
- **WHEN** workspace 目录是 `data/workspaces/<scope>`
- **THEN** 校验通过，正常挂载

### Requirement: 容器复用受 config-hash 失效

容器按名复用时 SHALL 校验其 config-hash 标签与当前期望配置（镜像、资源档、注入变量名集合、workspace 路径）一致；不一致时 MUST 销毁旧容器并按新配置重建，而非沿用旧配置容器。config-hash 只取注入变量的名字集合，不取其值（值变化不触发重建）。

#### Scenario: 配置变更触发重建
- **WHEN** 复用一个存活容器，但其 config-hash 标签与当前期望不一致
- **THEN** 销毁该容器并按当前配置重建

#### Scenario: 配置一致则复用
- **WHEN** 存活容器的 config-hash 与期望一致
- **THEN** 直接复用，不重建

#### Scenario: 仅 env 值变化不重建
- **WHEN** 注入变量名集合不变、仅某变量的值变化
- **THEN** config-hash 不变，容器照常复用

