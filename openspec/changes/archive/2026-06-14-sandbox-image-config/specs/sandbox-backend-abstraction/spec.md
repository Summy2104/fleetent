## MODIFIED Requirements

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
