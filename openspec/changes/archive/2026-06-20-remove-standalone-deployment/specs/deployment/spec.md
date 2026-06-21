## ADDED Requirements

### Requirement: 两种部署拓扑,platform 始终在场

系统 SHALL 只支持两种部署拓扑:**单机** 与 **分布式**,二者 platform 均始终在场。SHALL NOT 支持"无 platform 的 standalone agent 部署"作为受支持模式。两拓扑机制一致,只差 co-location:

- **单机**:platform + node + agent(+ kb-worker)同机;node 经 localhost desired-state 拉起/监管本机 agent;数据底座=本地文件。
- **分布式**:platform 一台、node + agent 在 agent host;node 经网络 desired-state 拉起本机 agent;数据底座=网络托管(见 substrate-backend-abstraction / network-substrate-backend)。

agent **永远由 node 拉起**(经 `fleetent agent run` 原语);agent 配置由 platform materialize 下发(非本机手写)。`fleetent agent run` 手跑仅 dev/test。

#### Scenario: 单机部署 = platform+node+agent 同机

- **WHEN** 单机部署
- **THEN** 同一台机跑 platform、node、agent;node 经 localhost 拉期望态并拉起 agent;无"无 platform"的 agent 进程作生产部署

#### Scenario: 不支持 standalone 部署

- **WHEN** 查阅部署文档 / 安装脚本
- **THEN** 没有"装一个 agent、不要 platform"的受支持部署路径;agent host 跑 node 接入 platform

#### Scenario: 两拓扑机制一致

- **WHEN** 对比单机与分布式
- **THEN** agent 启动(node 拉起)、ingest(worker)、数据(substrate)机制相同,只在 co-location 与后端选择上不同
