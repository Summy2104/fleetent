# sandbox-resource-limits（delta）

## ADDED Requirements

### Requirement: 资源配置字段按后端归属消费

`SandboxResources` 的字段 SHALL 按后端归属消费：通用字段（`memory`、`cpus`、`network`、`exec_timeout`、`read_only`）为接口契约，每个后端 MUST 映射到等价的资源/隔离原语；Docker 专属硬化字段（`pids_limit`、`tmpfs_size_mb`、`cap_drop_all`、`cap_add`、`no_new_privileges`、`init`、`run_as_user`）MUST 仅由 Docker 后端渲染，其他后端 MUST 忽略且不报错。字段归属 MUST 在数据类文档中标注。既有 Docker 渲染需求（`docker run` 旗标构造）不变，约束 Docker 后端。

#### Scenario: 通用字段在 microsandbox 后端生效
- **WHEN** microsandbox 后端以 `memory=512`、`cpus=1.0` 创建工作区
- **THEN** microVM 以等价的内存与 CPU 限制启动

#### Scenario: Docker 专属字段在其他后端被忽略
- **WHEN** microsandbox 后端收到含 `pids_limit`、`cap_drop_all` 等字段的资源配置
- **THEN** 工作区正常创建，这些字段不产生任何效果也不报错

#### Scenario: Docker 后端行为不变
- **WHEN** Docker 后端以同一资源配置创建容器
- **THEN** 通用字段与硬化字段的 `docker run` 旗标渲染与引入抽象前一致
