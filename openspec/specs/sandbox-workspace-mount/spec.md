# sandbox-workspace-mount Specification

## Purpose
TBD - created by archiving change sandbox-workspace. Update Purpose after archive.
## Requirements
### Requirement: Workspace 根目录从 paths 派生且可注入

系统 SHALL 从 `paths.py` 统一派生 workspace 根目录（`data_dir()/workspaces`），不得在沙箱模块内自读家目录环境变量。该路径常量 MUST 可通过 monkeypatch 注入，使测试隔离到临时目录而不触碰真实 `data/`。

#### Scenario: 默认派生
- **WHEN** 进程在仓库内运行且未设置 `FLEETENT_HOME`
- **THEN** workspace 根目录解析为仓库本地 `./data/workspaces`

#### Scenario: 测试注入隔离
- **WHEN** 测试 monkeypatch workspace 根常量为 `tmp_path` 下的目录
- **THEN** 所有 workspace 读写发生在该临时目录，不触碰真实 `data/`

### Requirement: Workspace 按 scope 映射进容器

系统 SHALL 为每个 scope（`session` 粒度用 session_id、`agent` 粒度用 agent_name，复用 `SandboxManager` 现有 Scope）维护独立的宿主 workspace 子目录，并在创建容器时通过 bind mount 映射到容器内固定挂载点 `/workspace`。同一 scope 的容器复用时 MUST 映射到同一宿主子目录。

#### Scenario: session scope 映射
- **WHEN** 以 session scope 为某 session_id 获取容器
- **THEN** 宿主 `data/workspaces/<session_id>/` 被 bind mount 到容器 `/workspace`

#### Scenario: 同 scope 复用同目录
- **WHEN** 同一 scope key 的容器被复用或重建
- **THEN** 映射到的宿主 workspace 子目录与首次一致

### Requirement: Workspace 持久化于容器生命周期之外

容器的停止、销毁或重建 SHALL NOT 删除宿主 workspace 目录及其内容。workspace 的内容在同 scope 的后续容器中 MUST 仍然可见。

#### Scenario: 容器销毁后数据保留
- **WHEN** 容器被销毁后，同 scope 再次获取新容器
- **THEN** 之前写入 `/workspace` 的文件在新容器中仍可读

### Requirement: Workspace 外宿主路径在容器内不可达

容器 SHALL NOT 挂载 workspace 以外的任何宿主路径。宿主的系统目录与凭证目录（如 `/etc`、`~/.ssh`、项目源码、`.env`）MUST NOT 通过容器可读；容器内访问这些路径只能得到容器自身镜像的内容（或不存在），不得触达宿主真实文件。

#### Scenario: 宿主敏感文件不可达
- **WHEN** 容器内读取 `/etc/passwd` 或宿主家目录下的凭证路径
- **THEN** 读到的是容器镜像自身的内容或路径不存在，宿主真实文件不被泄露

