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

在声明 `workspace_mount` capability 的后端（Docker）上，系统 SHALL 为每个 scope（`session` 粒度用 session_id、`agent` 粒度用 agent_name，复用 `SandboxManager` 现有 Scope）维护独立的宿主 workspace 子目录，并在创建容器时通过 bind mount 映射到容器内固定挂载点 `/workspace`。同一 scope 的容器复用时 MUST 映射到同一宿主子目录。

宿主 workspace 子目录名的 key 派生 MUST 与容器名采用同样的无碰撞规则：基于**完整未截断**的 scope key 计算，使两个不同 scope key MUST NOT 映射到同一宿主子目录，**即便它们共享超过子目录名长度上限的相同前缀、仅在被截断的尾部不同**。这是 `agent-data-isolation` 跨会话/跨归属数据隔离在 workspace 文件层的结构性保证，而非仅靠 key 截断后的偶然区分。

后端未声明 `workspace_mount` 时，获取工作区 MUST 不传递任何宿主挂载（容器内 `/workspace` 为实例本地目录，不与宿主共享）；文件工具按 `file-tools-sandbox-execution` 的降级条款走宿主围栏执行。此时 `run_code` 容器内视图与文件工具宿主视图分歧为已知限制，降级 MUST 记录一条说明日志。

#### Scenario: session scope 映射
- **WHEN** Docker 后端下以 session scope 为某 session_id 获取容器
- **THEN** 宿主 `workspaces` 根下由该 session_id 无碰撞派生的子目录被 bind mount 到容器 `/workspace`

#### Scenario: 同 scope 复用同目录
- **WHEN** Docker 后端下同一 scope key 的容器被复用或重建
- **THEN** 映射到的宿主 workspace 子目录与首次一致

#### Scenario: 超截断边界的同前缀 key 映射到不同目录
- **WHEN** 两个 scope key 共享超过子目录名长度上限的相同前缀、仅在会被截断的尾部不同
- **THEN** 两者映射到不同的宿主 workspace 子目录，一方写入 `/workspace` 的文件对另一方的容器不可见

#### Scenario: 不支持挂载的后端不传宿主路径
- **WHEN** 选定后端未声明 `workspace_mount`，为任一 scope 获取工作区
- **THEN** 创建调用不携带宿主挂载路径，记录一条降级说明日志，工作区仍可正常创建与执行

### Requirement: Workspace 持久化于容器生命周期之外

容器的停止、销毁或重建 SHALL NOT 删除宿主 workspace 目录及其内容。workspace 的内容在同 scope 的后续容器中 MUST 仍然可见。

#### Scenario: 容器销毁后数据保留
- **WHEN** 容器被销毁后，同 scope 再次获取新容器
- **THEN** 之前写入 `/workspace` 的文件在新容器中仍可读

### Requirement: Workspace 外宿主路径在容器内不可达

容器 SHALL NOT 挂载 workspace 与本 scope 归属 exchange 视图以外的任何宿主路径。宿主的系统目录与凭证目录（如 `/etc`、`~/.ssh`、项目源码、`.env`）MUST NOT 通过容器可读；容器内访问这些路径只能得到容器自身镜像的内容（或不存在），不得触达宿主真实文件。exchange 视图挂载 MUST 为只读且 MUST 仅含当前 run scope 归属的工件（见 file-exchange 归属视图）。

#### Scenario: 宿主敏感文件不可达

- **WHEN** 容器内读取 `/etc/passwd` 或宿主家目录下的凭证路径
- **THEN** 读到的是容器镜像自身的内容或路径不存在，宿主真实文件不被泄露

#### Scenario: 视图挂载不放大可达面

- **WHEN** 容器内枚举 `/exchange` 下内容
- **THEN** 仅见当前 run scope 归属的工件硬链接，无其他宿主路径

### Requirement: scope 归属视图只读挂载为容器 /exchange

在声明 `exchange_mount` capability 的后端上，系统 SHALL 在创建容器时把该 run 的 scope 归属视图目录（按 `scope_key` 定位，与 `/workspace` 同源）以只读 bind mount 映射到容器内固定挂载点 `/exchange`。同一 scope_key 的容器复用时 MUST 映射同一视图目录。挂载后视图目录内新增的硬链接 MUST 在容器内即时可见（无需重建容器）。容器内对 `/exchange` 的写入 MUST 失败（只读），产物仅能落 `/workspace`。

后端未声明 `exchange_mount` 时，获取容器 MUST 不传递视图挂载；容器内消费 `/exchange` 路径走 staging 降级：exec 前对代码中出现的 `/exchange/...` 引用做归属校验，通过者复制进容器后执行，且 MUST 记录一条降级说明日志。

#### Scenario: 容器先建文件后到

- **WHEN** 容器创建后某工件登记归属本 scope，视图目录新增硬链接
- **THEN** 容器内 `/exchange` 下该文件立即可读，无需重建容器

#### Scenario: 容器内 /exchange 只读

- **WHEN** 容器内代码尝试写 `/exchange/srv/x.txt`
- **THEN** 写入失败（只读挂载），`/workspace` 写入不受影响

#### Scenario: 无 exchange_mount 能力降级 staging

- **WHEN** 选定后端未声明 `exchange_mount`，run_code 代码引用本 scope 归属的 `/exchange` 文件
- **THEN** exec 前该文件经归属校验后被复制进容器对应路径，代码正常执行，并记录降级日志

