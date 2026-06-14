## ADDED Requirements

### Requirement: Bind mount 规格对 scope key 特殊字符鲁棒

在声明 `workspace_mount` / `exchange_mount` capability 的后端（Docker）上，workspace 与 scope 归属 exchange 视图的宿主 bind mount MUST 用对源路径中的 `:` 等字符鲁棒的挂载语法装配，使得当 `scope_key`（session 作用域下即 `session_id`，形如 `slack:dm:U…:<ts>`，含冒号）出现在挂载源路径中时，容器创建命令仍是合法 mount 规格、容器 MUST 能正常创建。MUST NOT 使用会因源路径含 `:` 而被错误切分的位置式 `-v <src>:<dst>` 语法承载可能含冒号的源路径。挂载点、只读语义、以及"无路径时不挂载"的行为 MUST 保持不变。

#### Scenario: 含冒号的 scope_key 视图挂载不破坏容器创建

- **WHEN** 某 run 的 `scope_key` 为含冒号的 session_id（如 `slack:dm:U1:1781443457.4`），其 exchange 视图目录路径据此包含冒号，Docker 后端为该 run 创建容器
- **THEN** 生成的 mount 规格合法（冒号不被误当字段分隔），容器创建成功，`/exchange` 只读挂载到该视图目录

#### Scenario: workspace 与 skill 挂载同样鲁棒

- **WHEN** Docker 后端装配 workspace（`/workspace`）或 skill（`/workspace/skills`）的 bind mount
- **THEN** 采用同一冒号安全语法，挂载点与只读语义不变，源路径含特殊字符不破坏 mount 规格

#### Scenario: 无源路径时不挂载

- **WHEN** workspace / exchange / skill 的宿主源路径为空或 None
- **THEN** 不向 `docker run` 添加任何对应的 mount 标志（行为与既有一致）
