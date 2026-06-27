## ADDED Requirements

### Requirement: 运行中部署的 build commit 可见
运行中的服务 SHALL 暴露其所基于的源码 build commit（短 SHA），使 operator 能确认线上实际运行的代码版本。该信息 SHALL 在服务启动时记录到结构化日志，并 MAY 经只读入口（如 `--version` 或健康字段）查询。

#### Scenario: 启动日志记录 build commit
- **WHEN** platform / node / kb-worker 任一服务启动
- **THEN** 结构化日志中包含该次构建对应的 build commit 短 SHA

#### Scenario: build commit 可查询
- **WHEN** operator 查询运行中部署的版本信息
- **THEN** 返回该部署构建时的 commit 短 SHA
- **AND** 当源码未提供 commit 信息时，返回明确的 "unknown" 而非静默空值

### Requirement: 部署版本陈旧检测
项目 SHALL 提供入口，对比「运行中部署的 build commit」与「源码目录当前 HEAD」，在二者不一致时明确提示部署已陈旧。该检测 SHALL 覆盖「`git pull` 了但未重新构建/部署」这一场景。

#### Scenario: 检出部署落后于源码
- **WHEN** 源码 HEAD 领先于运行中部署的 build commit
- **THEN** 检测入口报告部署陈旧
- **AND** 输出运行中 commit 与源码 HEAD commit 供对照

#### Scenario: 部署与源码一致时报告最新
- **WHEN** 运行中部署的 build commit 等于源码 HEAD
- **THEN** 检测入口报告部署为最新

### Requirement: 一键重部署入口
项目 SHALL 提供单一重部署入口，原子地完成「从当前源码重新构建」+「重启受影响服务」，使 operator 无需手动串联多步。重部署 SHALL 在重启前完成构建，构建失败时 SHALL NOT 重启正在运行的服务。

#### Scenario: 重部署重建并重启
- **WHEN** operator 触发一键重部署
- **THEN** 先从当前源码重新构建镜像/二进制
- **AND** 构建成功后重启受影响服务
- **AND** 重启后运行中部署的 build commit 等于源码 HEAD

#### Scenario: 构建失败不影响在运行服务
- **WHEN** 重部署的构建步骤失败
- **THEN** 入口返回非 0 exit code
- **AND** 不重启正在运行的服务（保持旧版本继续提供服务）

### Requirement: platform serve 默认端口与客户端默认一致
`fleetent platform serve` 在未显式传 `--port` 时 SHALL 绑定与客户端默认一致的端口（8765），使不带参数启动的 platform 与默认 TUI / 文档约定可直接连通。

#### Scenario: 不带 --port 启动绑 8765
- **WHEN** operator 运行 `fleetent platform serve`（不带 `--port`）
- **THEN** platform 绑定 8765
- **AND** 默认 TUI（`ws://127.0.0.1:8765/ws`）无需额外配置即可连通

#### Scenario: 显式 --port 仍优先
- **WHEN** operator 运行 `fleetent platform serve --port <P>`
- **THEN** platform 绑定 `<P>`（显式参数优先于默认）
