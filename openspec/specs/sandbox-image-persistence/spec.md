# sandbox-image-persistence Specification

## Purpose
TBD - created by archiving change sandbox-workspace-scope-split. Update Purpose after archive.
## Requirements
### Requirement: 依赖镜像经声明式离线构建为不可变镜像

per-agent 依赖持久化 SHALL 通过**声明式离线构建**实现:agent 预声明的 `setup_command`(依赖安装步骤)在**离线构建阶段**执行,产出一个**不可变**依赖镜像(deps 层);运行期容器 SHALL 以**只读** rootfs 从该不可变镜像启动。构建在没有终端用户会话数据介入的封闭环境中进行,产出的镜像内容 MUST NOT 包含任何终端用户运行期写入的状态。该开关 SHALL 独立于 `workspace_scope`(数据隔离粒度),二者可分别配置。

#### Scenario: 声明式构建产出不可变镜像
- **WHEN** 某 agent 声明了 `setup_command` 且 per-agent 镜像持久化开启,触发离线构建
- **THEN** 构建在封闭环境执行 `setup_command`,产出一个不可变依赖镜像,运行期容器以只读 rootfs 从该镜像启动,先前声明的依赖无需在运行期重装

#### Scenario: 镜像选择只看持久化开关与后端能力
- **WHEN** 为某 agent 取得容器,决定是否使用依赖镜像
- **THEN** 是否启用依赖镜像仅由 per-agent 镜像持久化开关与后端 `persist_workspace` 能力决定,与 `workspace_scope` 取值无关

### Requirement: 禁用从运行容器固化镜像

生命周期层 SHALL NOT 通过对**运行中(已被会话改写过 rootfs)的容器**执行镜像固化(如 `docker commit`-from-running-container)来持久化依赖。闲置回收 MUST NOT 在销毁前固化运行容器;`sweep_idle` SHALL 仅按容器存活/闲置回收,不产出镜像。理由:对运行容器固化会把某次会话写入容器层的内容(site-packages、`sitecustomize.py`、临时文件)烤进下一次启动的镜像,污染流向后续会话,且 `--read-only` / `--network none` 等运行期加固对已烤进镜像层的内容无效。

#### Scenario: 回收不固化运行容器
- **WHEN** 某依赖镜像持久化的容器闲置超时被回收
- **THEN** 回收路径直接销毁容器,不对其执行任何 from-running-container 的镜像固化,不产出镜像

#### Scenario: 重建不带入上次会话写入
- **WHEN** 某容器被回收后,同一 agent 再次取得容器并从声明式不可变镜像启动
- **THEN** 新容器仅包含不可变镜像的声明依赖,不包含上一会话写入容器层的任何内容

#### Scenario: 镜像选择查声明式产物而非固化产物
- **WHEN** 为某 agent 取得容器并查找可用依赖镜像
- **THEN** 查找的是声明式离线构建的不可变镜像标签,不查找任何 from-running-container 固化产生的镜像;无声明式镜像时回退基础镜像

### Requirement: 镜像持久化按后端 persist_workspace 能力分级

依赖镜像持久化 SHALL 按后端 `persist_workspace` 能力分级。后端声明 `persist_workspace=True`(Docker)时 MUST 支持构建并复用不可变依赖镜像,运行期从 deps 层秒级热启动。后端声明 `persist_workspace=False`(microsandbox,无 image-commit 原语)时,秒级热启动 MUST 被声明为**不成立**——运行期从基础镜像 + setup 重新就绪(依赖需在运行期重新安装),且该限制 MUST 在文档与运行期日志中明示,MUST NOT 让调用方误以为依赖已被持久化为可热启动镜像。

#### Scenario: 支持持久化的后端热启动
- **WHEN** Docker 后端下某 agent 已有声明式不可变依赖镜像
- **THEN** 运行期容器从该 deps 层只读热启动,依赖即时可用,无需重新安装

#### Scenario: 不支持持久化的后端声明热启动不成立
- **WHEN** microsandbox 后端(`persist_workspace=False`)下为某 agent 取得容器
- **THEN** 容器从基础镜像启动并经 setup 重新就绪,记录一条「该后端不支持依赖镜像热启动、运行期重新就绪」说明日志,不查找也不依赖任何持久化依赖镜像

