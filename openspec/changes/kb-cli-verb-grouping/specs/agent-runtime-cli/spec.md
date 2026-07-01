## MODIFIED Requirements

### Requirement: `fleetent kb worker` 子命令

`fleetent` 命令 SHALL 以 `kb` 顶层名词分组 KB 服务子命令（对齐 `agent`/`platform`/`node` 的"名词 + 子命令"约定），其中 SHALL 提供 `kb worker` 子命令,启动 KB ingest 队列的唯一消费者长驻进程。其 import SHALL 懒加载,不在 `fleetent agent run` 启动路径触发(对齐 `fleetent node start` 模式)。worker SHALL NOT `import fleetent.platform.*`。旧的扁平连字符形式 `fleetent kb-worker` SHALL NOT 再存在(一刀切,无兼容别名)。

#### Scenario: kb worker 启动并消费

- **WHEN** 用户运行 `fleetent kb worker`
- **THEN** 进程进入循环:claim pending job → 调 ingest 核 → mark done/failed

#### Scenario: agent run 不加载 kb worker

- **WHEN** 调度到 `fleetent agent run` 分支
- **THEN** `fleetent kb worker` 的实现模块未被 import(懒加载)

#### Scenario: 旧扁平命令名已移除

- **WHEN** 用户运行 `fleetent kb-worker`(旧连字符形式)
- **THEN** 命令不被识别(不存在该入口);KB 子命令统一经 `fleetent kb <verb>` 调用
