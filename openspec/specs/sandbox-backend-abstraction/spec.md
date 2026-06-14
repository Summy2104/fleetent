# sandbox-backend-abstraction Specification

## Purpose
Pluggable sandbox backend contract: ABC surface, capability declarations, factory selection + config precedence, and capability-gated degradation shared by all backends.
## Requirements
### Requirement: 统一后端抽象接口承载沙箱执行面

沙箱执行面 SHALL 由统一的后端抽象基类承载：核心面（可用性探测 `available`、按名创建 `create_workspace`、按名查找 `find_workspace`、命令执行 `exec`、销毁 `destroy_workspace`、强制终止 `kill_workspace`）MUST 由每个后端实现；capability 门控面（依赖固化 `commit_workspace` / `image_exists`、按前缀枚举 `list_workspaces`）仅由声明支持的后端实现，未声明支持时调用方 MUST NOT 调用。session-snapshot 连续性（env/cwd 跨 exec）的包装逻辑与状态 MUST 在基类模板方法中实现，对所有后端行为一致；子类只实现执行原语。

#### Scenario: 核心面在任一后端可用
- **WHEN** 任一已配置后端被选定，调用方执行创建、查找、执行、销毁
- **THEN** 各操作经该后端完成，调用方代码不含后端类型分支

#### Scenario: 连续性包装跨后端一致
- **WHEN** 同一 session 在任一后端先 `export FOO=bar` 再 `echo $FOO`
- **THEN** 第二条命令输出 `bar`——连续性由基类模板方法提供，与后端无关

#### Scenario: 门控方法在不支持的后端不被调用
- **WHEN** 选定后端未声明某 capability（如依赖固化）
- **THEN** 对应门控方法不被生命周期层调用，不发生「stub 假装成功」或异常

### Requirement: 后端声明 capability 且决策点按 capability 分支

每个后端 SHALL 声明一组 capability（`persist_workspace` 依赖固化、`workspace_mount` 宿主目录挂载、`orphan_cleanup` 按前缀枚举、`exchange_mount` 会话归属视图只读挂载）。生命周期、清理、挂载等决策点 MUST 按所声明 capability 分支决定行为，MUST NOT 以后端具体类型（isinstance 或等价判断）分支。Docker 后端四项 capability 均 MUST 为真（既有三项行为与现状一致，`exchange_mount` 为本变更新增）。

#### Scenario: Docker 后端全量 capability

- **WHEN** 选定 Docker 后端
- **THEN** 依赖固化、宿主挂载、按前缀枚举行为与引入抽象前完全一致，且容器创建携带 exchange 归属视图只读挂载

#### Scenario: 决策点不感知后端类型

- **WHEN** 新增一个声明了 capability 的后端
- **THEN** 生命周期/清理/挂载决策点无需修改即按其 capability 取得正确行为

#### Scenario: 无 exchange_mount 的后端走降级

- **WHEN** 选定后端未声明 `exchange_mount`
- **THEN** 容器创建不携带视图挂载，`/exchange` 消费按 sandbox-workspace-mount 的 staging 降级条款执行

### Requirement: 后端选择经配置解析且有明确优先级

后端选择 SHALL 经配置解析：`platform.yaml` 的 `sandbox.backend`（取值 `docker` | `microsandbox`）为全局默认，`agent.yaml` 的 `sandbox.backend` 为 per-agent 覆盖。优先级 MUST 为：agent.yaml 显式值 > platform.yaml > 默认 `docker`。非法取值 MUST NOT 被静默接受——记录警告并回退 `docker`。单体 agent 独立运行（无 platform.yaml）时 MUST 可仅凭 agent.yaml 完成全部后端配置。

后端的**基础镜像**亦 SHALL 可配且遵循同一优先级：Docker 后端读 `sandbox.docker.image`、microsandbox 后端读 `sandbox.microsandbox.image`，均为 `platform.yaml` 全局默认叠加 `agent.yaml` 每-agent 覆盖（agent > platform > 后端内置默认）。Docker 后端在 `sandbox.docker.image` 未配置时 MUST 仍使用内置默认 `python:3.12-slim`（向后兼容）。镜像配置 MUST NOT 改变沙箱的网络/隔离策略（镜像只决定运行时依赖，禁网等隔离仍由运行时 flag 施加）。

#### Scenario: 未配置时默认 docker
- **WHEN** platform.yaml 与 agent.yaml 均未声明 `sandbox.backend`
- **THEN** 选定 Docker 后端，行为与现状一致

#### Scenario: agent.yaml 覆盖 platform.yaml
- **WHEN** platform.yaml 声明 `backend: docker`，agent.yaml 声明 `backend: microsandbox`
- **THEN** 该 agent 进程选定 microsandbox 后端

#### Scenario: 非法值回退并告警
- **WHEN** 配置声明 `sandbox.backend: firecracker`（未知取值）
- **THEN** 记录警告并回退 Docker 后端，不以非法值启动

#### Scenario: 单体 agent 仅凭 agent.yaml 配全
- **WHEN** 单体 agent 独立运行（home 根无 platform.yaml），agent.yaml 声明 `sandbox.backend: microsandbox` 及连接配置
- **THEN** 进程以 microsandbox 后端启动，不依赖任何 platform 配置文件

#### Scenario: Docker 镜像未配置用内置默认
- **WHEN** `sandbox.docker.image` 在 platform.yaml 与 agent.yaml 均未声明
- **THEN** Docker 后端以内置默认 `python:3.12-slim` 启动容器，行为与现状一致

#### Scenario: Docker 镜像可配且 agent 覆盖平台
- **WHEN** platform.yaml 声明 `sandbox.docker.image: fleetent-sandbox:1`，agent.yaml 声明 `sandbox.docker.image: fleetent-sandbox:2`
- **THEN** 该 agent 的 Docker 沙箱容器以 `fleetent-sandbox:2` 启动（agent 覆盖平台）

### Requirement: SandboxClient 兼容 shim 保留既有导入面

`integrations/sandbox/client.py` SHALL 退化为 re-export shim（`SandboxClient` = Docker 后端实现），包 `__init__` 继续导出 `SandboxClient` 名称。既有 `from fleetent.integrations.sandbox import SandboxClient` 导入 MUST 不受破坏。

#### Scenario: 旧导入路径仍可用
- **WHEN** 既有代码以旧路径导入并实例化 `SandboxClient`
- **THEN** 取得 Docker 后端实例，行为与迁移前一致

