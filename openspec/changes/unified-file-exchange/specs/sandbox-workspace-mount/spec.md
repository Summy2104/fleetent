# sandbox-workspace-mount Delta

## MODIFIED Requirements

### Requirement: Workspace 外宿主路径在容器内不可达

容器 SHALL NOT 挂载 workspace 与本 scope 归属 exchange 视图以外的任何宿主路径。宿主的系统目录与凭证目录（如 `/etc`、`~/.ssh`、项目源码、`.env`）MUST NOT 通过容器可读；容器内访问这些路径只能得到容器自身镜像的内容（或不存在），不得触达宿主真实文件。exchange 视图挂载 MUST 为只读且 MUST 仅含当前 run scope 归属的工件（见 file-exchange 归属视图）。

#### Scenario: 宿主敏感文件不可达

- **WHEN** 容器内读取 `/etc/passwd` 或宿主家目录下的凭证路径
- **THEN** 读到的是容器镜像自身的内容或路径不存在，宿主真实文件不被泄露

#### Scenario: 视图挂载不放大可达面

- **WHEN** 容器内枚举 `/exchange` 下内容
- **THEN** 仅见当前 run scope 归属的工件硬链接，无其他宿主路径

## ADDED Requirements

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
