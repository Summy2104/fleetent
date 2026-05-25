## Context

`server.py` lifespan 已经管理 MCP 连接、Slack/Telegram 适配器的启动与关闭，模式统一：`asyncio.create_task()` 启动后台服务，lifespan yield 后 cleanup。`agent_loop.run()` 是同步触发 agent 的核心入口（非流式），返回 reply string，已被 normalizer 和 CLI 复用。`config/` 目录有 `mcp.yaml`、`settings.yaml`，YAML 文件格式一致。`tools.py` 注册内置工具，`@tool(risk_level=...)` 装饰器走 permission gate。

## Goals / Non-Goals

**Goals:**
- APScheduler 管理 cron 调度，支持标准 5 字段 cron 表达式 + timezone
- 静态任务从 `config/cron.yaml` 加载（服务重启不丢失）
- 动态任务通过 admin CLI 或 `schedule_task` 工具创建，持久化到 SQLite
- 每次触发：`asyncio.create_task(agent_loop.run(...))` 异步执行，不阻塞调度器
- reply_func 为 no-op，结果记录到 eval trace

**Non-Goals:**
- 任务执行状态跟踪（成功/失败历史）——eval trace 已有记录，不单独建表
- 分布式调度（单进程，SQLite 够用）
- 间隔任务（interval）和一次性任务（date）——第一版只做 cron
- 任务并发控制（同一任务上次还没跑完，新触发是否跳过）

## Decisions

### 1. APScheduler 3.x + MemoryJobStore，SQLite 由我们自己管

APScheduler 的 SQLAlchemy JobStore 需要额外依赖且配置复杂。用 MemoryJobStore（默认）+ 我们自己的 `schedule_store.py` 管持久化：启动时从 SQLite 读取所有 enabled 任务并注册到 APScheduler，动态添加时同时写 SQLite 和调用 `scheduler.add_job()`。模式与项目其他 SQLite 模块一致，测试也容易用 `monkeypatch` 隔离。

### 2. `cron_scheduler.py` 作为调度器封装，不内联到 `server.py`

职责独立：调度器管"何时触发"，`server.py` 管"何时启动/停止"。`cron_scheduler.py` 暴露 `start()`、`shutdown()`、`add_job()`、`remove_job()` 四个接口，`server.py` lifespan 只调用 start/shutdown。

### 3. 触发逻辑：`asyncio.create_task(run_job(job_def))`

APScheduler 的 AsyncIOScheduler 在 event loop 中触发，任务函数是 async 的。每次触发调用：
```python
async def _fire(job: ScheduledTask) -> None:
    await asyncio.get_event_loop().run_in_executor(
        None, agent_loop.run_sync, job.message, job.user_id
    )
```
`run_sync` 已有，内部用 `asyncio.run(run(...))` — 注意：不能在已有 event loop 中直接 `asyncio.run()`，需要用 `run_in_executor` 在线程池执行。或者直接用 `await agent_loop.run(messages, user_id=...)` 构造 messages。

**修正**：直接 `await agent_loop.run(messages, user_id=job.user_id)` 构造初始 messages 列表，比 run_sync 更干净，避免 nested event loop 问题。

### 4. `schedule_task` 工具 risk_level="high"，`cancel_task` risk_level="medium"

创建定时任务是高权限操作（相当于注入持久化后台代码），必须经过 human approval。取消任务相对安全，medium 即可。

### 5. SQLite schema

```sql
CREATE TABLE IF NOT EXISTS scheduled_tasks (
    id         TEXT PRIMARY KEY,      -- UUID
    name       TEXT NOT NULL,
    cron_expr  TEXT NOT NULL,         -- "0 9 * * 1-5"
    timezone   TEXT NOT NULL DEFAULT 'UTC',
    user_id    TEXT NOT NULL,
    agent_name TEXT,                  -- NULL = use default agent resolution
    message    TEXT NOT NULL,         -- prompt text to run
    enabled    INTEGER NOT NULL DEFAULT 1,
    source     TEXT NOT NULL DEFAULT 'dynamic',  -- 'static'|'dynamic'|'tool'
    created_at TEXT NOT NULL
)
```

`source` 字段区分来源：static (cron.yaml) / dynamic (admin CLI) / tool (agent 创建)。

### 6. config/cron.yaml 格式

```yaml
jobs:
  - id: daily-standup
    name: "Daily Standup Report"
    cron: "0 9 * * 1-5"
    timezone: "Asia/Shanghai"
    user_id: "uuid-of-user"
    agent_name: "analyst"          # optional
    message: "Generate today's standup report"
```

### 7. 与 webhook 一致：reply_func 为 no-op

cron 触发的 agent run 结果写 eval trace，不需要回推。未来可以扩展 `reply_channel` 字段把结果转发到 Slack/Telegram，但不在本 change 范围内。

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| APScheduler 在 asyncio event loop 中调用阻塞的 `agent_loop.run_sync` | 使用 `await agent_loop.run()` 直接 async 调用，绕开 nested loop 问题 |
| 服务重启后 static jobs 和 dynamic jobs 都需要重新注册 | 启动时统一从 SQLite + cron.yaml 加载，逻辑对称，无特殊路径 |
| `schedule_task` 工具被滥用（agent 无限创建任务） | risk_level="high" 要求人工审批；admin CLI 可查看和删除 |
| cron.yaml 中 user_id 引用不存在的用户 | 启动时只加载不验证，触发时 agent_loop 会因 user_id 无效失败，错误写 trace |

## Migration Plan

1. `uv add apscheduler` 添加依赖
2. 新增 `schedule_store.py`、`cron_scheduler.py`（纯新文件）
3. `server.py` lifespan 加 scheduler start/shutdown（3 行改动）
4. `tools.py` 加两个工具（import schedule_store）
5. `admin.py` 加三个命令
6. 无数据迁移，无现有行为变更
