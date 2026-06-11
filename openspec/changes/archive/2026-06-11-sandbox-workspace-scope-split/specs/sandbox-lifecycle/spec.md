## MODIFIED Requirements

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
