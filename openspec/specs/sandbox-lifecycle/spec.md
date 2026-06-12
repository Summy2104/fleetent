# sandbox-lifecycle Specification

## Purpose
TBD - created by archiving change sandbox-lifecycle. Update Purpose after archive.
## Requirements
### Requirement: 沙箱容器按 scope 决定存活粒度

沙箱生命周期层 SHALL 支持两种存活粒度（scope）：`session`（默认）与 `agent`。`session` scope 的容器以会话为归属边界，`agent` scope 的容器以 agent 定义为归属边界。每个容器 MUST 有唯一且编码了归属信息的名称，scope 与归属 key 不同的请求 MUST 取得相互隔离的容器。

容器名中编码归属的稳定标识 MUST 基于**完整未截断**的归属 key 计算——当容器名受长度上限约束需要截断时，名称中 MUST 包含一段由完整 key 派生的无碰撞标识（如可读前缀 + 完整 key 的哈希后缀），使任意两个不同归属 key MUST NOT 产生相同容器名，**即便它们共享超过长度上限的相同前缀、仅在被截断的尾部不同**。

#### Scenario: session scope 默认生效
- **WHEN** 配置未显式指定 scope，沙箱生命周期层为某会话取得容器
- **THEN** 该容器以 `session` scope 创建，名称编码了该会话的归属信息

#### Scenario: 不同归属取得隔离容器
- **WHEN** 两个不同 session（或两个不同 agent）分别取得沙箱容器
- **THEN** 两者得到名称不同、相互隔离的容器，一方在容器内产生的状态对另一方不可见

#### Scenario: 超截断边界的同前缀 key 不碰撞
- **WHEN** 两个归属 key 共享超过容器名长度上限的相同前缀、仅在会被截断的尾部不同（例如同一长前缀下的两个不同会话标识）
- **THEN** 两者仍取得名称不同、相互隔离的容器，任何一方在容器内产生的状态对另一方不可见

### Requirement: session scope 会话内复用、会话结束销毁

在 `session` 数据隔离粒度(`workspace_scope=session`)下,同一会话内多次请求沙箱执行 SHALL 复用同一**存活**容器(已存在且存活则不新建;已死则按「死容器自愈」requirement 重建);会话结束时该容器 MUST 被销毁。`session` 数据隔离粒度由 `workspace_scope` 单独决定,与依赖镜像持久化无关(后者见 `sandbox-image-persistence`)。

#### Scenario: 同一会话内复用容器
- **WHEN** 同一会话内第二次请求沙箱执行且首次创建的容器仍存活
- **THEN** 复用首次创建的同一容器,不新建容器

#### Scenario: 会话结束销毁容器
- **WHEN** 会话结束并触发释放
- **THEN** 该会话的 `session` 数据隔离容器被销毁并从登记中移除,不影响其它会话的容器

### Requirement: agent scope 闲置超时自动销毁

容器存活粒度由 `workspace_scope` 决定;闲置回收 SHALL 仅按容器闲置时间清理。`agent` 归属(仅 single-tenant 数据隔离)容器闲置时间超过配置的 `idle_hours`(默认 2 小时)时,闲置回收 SHALL 销毁该容器;`session` 归属容器 MUST NOT 参与闲置回收。销毁前 MUST NOT 对运行容器执行任何镜像固化——依赖镜像持久化已与容器存活解耦,改由声明式离线构建提供(见 `sandbox-image-persistence`),故 `sweep_idle` 仅按存活回收、不产出镜像。

#### Scenario: 超时容器被回收
- **WHEN** 某 `agent` 归属容器距上次使用超过 `idle_hours`,触发闲置回收
- **THEN** 该容器被直接销毁,回收路径不对其执行 from-running-container 的镜像固化

#### Scenario: 未超时容器保留
- **WHEN** 某 `agent` 归属容器距上次使用未超过 `idle_hours`,触发闲置回收
- **THEN** 该容器被保留,不受影响

### Requirement: agent scope 以可写 rootfs 创建，依赖固化按后端 capability 执行

容器创建时的镜像选择 SHALL 与容器存活粒度(`workspace_scope`)**解耦**:是否以依赖镜像启动仅由 per-agent 镜像持久化开关与后端 `persist_workspace` 能力决定(见 `sandbox-image-persistence`),MUST NOT 由 `workspace_scope` 取值驱动。运行期容器 SHALL 以只读 rootfs + `network=none` 启动;依赖的获得依赖**离线构建的不可变镜像**而非运行期写入可写 rootfs 后再固化。`acquire` / `_image_for` / `sweep_idle` / `_Entry` 的 key 派生中心不变式(同 key→同容器名→同 workspace 目录)MUST 保持,但容器名/路径 key 来源 MUST 收敛到 `workspace_scope`,镜像选择 MUST 走独立分支。

依赖镜像持久化按后端 capability 分支:

- 后端声明 `persist_workspace`(Docker)时,依赖经声明式离线构建产出不可变镜像;取得容器时若该 agent 已有不可变依赖镜像,SHALL 以其为基础镜像只读热启动,无需重装依赖;无声明式镜像时回退基础镜像
- 后端未声明 `persist_workspace`(microsandbox)时,生命周期层 MUST NOT 查找或依赖任何持久化依赖镜像,也 MUST NOT 对运行容器调用固化方法;取得容器 MUST 从基础镜像启动(依赖运行期重新就绪),并记录一条说明日志明示热启动不成立

> 设计依据:对运行容器 `docker commit` 会把某次会话写入容器层的内容(site-packages、`sitecustomize.py`、临时文件)烤进后续镜像、污染其他会话,且运行期加固对已 baked 内容无效;故依赖持久化改为离线构建不可变镜像 + 运行期只读启动,与容器存活粒度彻底解耦,可写 rootfs 不再是依赖固化的前提。

#### Scenario: 镜像选择不随 workspace_scope 改变
- **WHEN** 在 `session` 与 `agent` 两种 `workspace_scope` 下分别取得容器,且 per-agent 镜像持久化开关与后端能力相同
- **THEN** 两次取得容器的镜像选择结果一致,镜像选择由独立分支(持久化开关 + 后端能力)决定而非 `workspace_scope`

#### Scenario: 支持持久化的后端从不可变镜像热启动
- **WHEN** Docker 后端下某 agent 已有声明式不可变依赖镜像,再次取得容器
- **THEN** 以该不可变镜像为基础镜像只读热启动,先前依赖即时可用,不重装依赖,且不依赖任何 from-running-container 固化产物

#### Scenario: 不支持持久化的后端回退基础镜像
- **WHEN** microsandbox 后端下为某 agent 取得容器
- **THEN** 从配置的基础镜像启动、依赖运行期重新就绪,不查找持久化依赖镜像,并记录一条热启动不成立的说明日志

### Requirement: 死容器自愈（复用前校验 + 执行失踪恢复）

`SandboxManager.acquire` 在注册表命中时 SHALL 先校验该容器存活；容器已不存在/不可用时 MUST 丢弃该注册项并按"收养或新建"路径取得新容器，MUST NOT 把死容器 id 交给执行层。执行层命中容器失踪类错误（如 `No such container`）时 SHALL 注销对应注册项并重试一次（重新 acquire 新容器）；重试仍失败 MUST 返回明确的沙箱基础设施错误。workspace 为 host 挂载，容器重建后此前写入 workspace 的文件 MUST 对新容器可见。

#### Scenario: 复用命中死容器时自动重建
- **WHEN** 注册表中登记的容器已被外部销毁（OOM/手工 rm/daemon 重启），同会话再次请求沙箱执行
- **THEN** acquire 丢弃失效注册项并创建新容器，本次调用在新容器中正常执行

#### Scenario: 执行时容器失踪自愈
- **WHEN** acquire 校验通过后、命令执行前容器死亡，执行返回容器失踪类错误
- **THEN** 该注册项被注销，本次调用经一次重试在新容器中完成；连续失败则返回明确的沙箱不可用错误

#### Scenario: 容器重建不丢工作区文件
- **WHEN** 容器死亡前已有文件写入 workspace（如 IM 入站附件），容器经自愈重建
- **THEN** 该文件在新容器的 `/workspace` 下仍可读取

