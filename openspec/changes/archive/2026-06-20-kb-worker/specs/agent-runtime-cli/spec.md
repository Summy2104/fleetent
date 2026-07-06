## ADDED Requirements

### Requirement: `fleetent kb worker` 子命令

`fleetent` 命令 SHALL 提供 `kb-worker` 子命令,启动 KB ingest 队列的唯一消费者长驻进程。其 import SHALL 懒加载,不在 `fleetent agent run` 启动路径触发(对齐 `fleetent node start` 模式)。worker SHALL NOT `import fleetent.platform.*`。

#### Scenario: kb-worker 启动并消费

- **WHEN** 用户运行 `fleetent kb worker`
- **THEN** 进程进入循环:claim pending job → 调 ingest 核 → mark done/failed

#### Scenario: agent run 不加载 kb-worker

- **WHEN** 调度到 `fleetent agent run` 分支
- **THEN** `fleetent kb worker` 的实现模块未被 import(懒加载)
