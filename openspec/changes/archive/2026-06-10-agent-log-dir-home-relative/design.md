## Context

`runtime/agent_app.py:_configure_logging_from_agent` 目前的解析逻辑：

```python
resolved_dir: str | Path = log.directory if log.directory else home_dir / "data" / "logs"
```

`directory` 非空时原样透传字符串，`structured_logging` 写文件时按进程 CWD 解析相对路径。配置在 agent.yaml 里、解析却挂在启动位置上，违背"agent home 自包含"直觉（agent.yaml、.env、data/ 都以家目录为根）。留空时代码已主动拼 `home_dir`，两条路径行为不一致。

## Goals / Non-Goals

**Goals:**
- `directory` 为相对路径时相对 agent 家目录解析，启动位置无关
- 绝对路径、留空两态行为完全不变

**Non-Goals:**
- platform 服务路径（`server.py` / `config.py:LoggingSettings`）的同类问题——归属 platform 侧，另行处理
- `structured_logging.py` 本体改动（解析责任留在调用方，与留空分支一致）

## Decisions

**D1 在 `_configure_logging_from_agent` 单点解析，不下沉到 `structured_logging`。**
`structured_logging` 是 agent 与 platform 共同消费的顶层基础设施，不知道也不应知道"agent home"概念；home 语义只存在于 agent runtime 边界。留空分支的 `home_dir / "data" / "logs"` 已在此处拼接，相对路径在同一处拼接保持对称。
- 备选：`configure_structured_logging` 加 `base_dir` 参数。否决——把调用方语义渗入基础设施层，platform 调用方还得传一个无意义的参数。

**D2 用 `Path.is_absolute()` 判别，相对即 `home_dir / directory`。**
语义最直接：`data/logs` → `home/data/logs`；`/var/log/fleetent` → 原样。无需引入新配置字段。

## Risks / Trade-offs

- [行为变更] 依赖旧"按 CWD 解析"行为的部署日志位置会迁移 → 该行为即缺陷本身，无已知合法使用；变更后位置更可预期
- [无] 绝对路径 / 留空两态有测试钉住，不受影响
