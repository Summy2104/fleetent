## Why

mini-agent 只能被动响应消息，完全没有主动触发机制。定时日报、周期性监控、每日提醒等场景无法支持——这些是 IM 场景里最高频的"自动化"需求，也是把 agent 从"工具"变成"同事"的关键能力。

## What Changes

- 新增 `schedule_store.py`：SQLite `scheduled_tasks` 表，管理动态创建的定时任务（CRUD + 持久化）
- 新增 `cron_scheduler.py`：APScheduler 封装，服务启动时从 `config/cron.yaml` 和 `schedule_store` 加载所有任务，每次触发调用 `agent_loop.run()`
- `config/cron.yaml`（示例文件）：静态定时任务定义，格式与 webhook/mcp 配置一致
- `tools.py` 新增两个内置工具：`schedule_task`（risk_level="high"）、`cancel_task`（risk_level="medium"），允许 agent 动态创建/取消定时任务
- `server.py` lifespan 启动/关闭调度器
- `admin.py` 新增 `list-schedules`、`add-schedule`、`remove-schedule` 命令
- 依赖：`apscheduler>=3.10`（纯 Python，无额外系统依赖）

## Capabilities

### New Capabilities

- `cron-scheduled-tasks`：按 cron 表达式定时触发 agent run，支持静态配置文件定义和运行时动态创建/取消，任务定义持久化到 SQLite

### Modified Capabilities

无

## Impact

- **代码**：新增 `cron_scheduler.py`、`schedule_store.py`；修改 `server.py`（lifespan）、`tools.py`（新工具）、`admin.py`（新命令）
- **依赖**：`apscheduler>=3.10`（需加入 `pyproject.toml`）
- **数据**：`data/users.db` 新增 `scheduled_tasks` 表
- **破坏性**：无，全部新增路径
