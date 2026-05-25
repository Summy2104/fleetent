## 1. 依赖与 schedule_store

- [x] 1.1 在 `pyproject.toml` 添加 `apscheduler>=3.10` 依赖，运行 `uv sync` 确认安装
- [x] 1.2 Write failing tests: `schedule_store.create()` 插入新行并返回含 UUID id 的 dict；`list_tasks()` 返回所有行；`delete(task_id)` 删除目标行；不存在 id 时 `delete` 静默返回
- [x] 1.3 新建 `schedule_store.py`：`_init_db()` 创建 `scheduled_tasks` 表；实现 `create(name, cron_expr, timezone, user_id, agent_name, message, source) -> dict`；`list_tasks() -> list[dict]`；`delete(task_id) -> bool`

## 2. cron_scheduler — 调度器封装

- [x] 2.1 Write failing tests: `CronScheduler.start()` 后 APScheduler 处于 running 状态；`add_job()` 注册 job 后 scheduler 中存在对应 job_id；`remove_job()` 后 job_id 消失；`shutdown()` 后 scheduler 停止
- [x] 2.2 新建 `cron_scheduler.py`：封装 `AsyncIOScheduler`；`start()` 从 `schedule_store.list_tasks()` 加载所有任务并注册；`add_job(task_dict)`；`remove_job(task_id)`；`shutdown()`
- [x] 2.3 Write failing tests: cron 触发时 `agent_loop.run()` 被以正确 user_id 和 message 调用（mock agent_loop.run）
- [x] 2.4 实现触发函数 `_fire(task: dict)`：构造 messages 列表，`await agent_loop.run(messages, user_id=task["user_id"])` 异步执行；用 `asyncio.create_task()` 包裹，不阻塞调度器

## 3. config/cron.yaml 加载

- [x] 3.1 Write failing tests: `load_cron_yaml(path)` 有效 YAML 时返回 job 列表；文件不存在时返回空列表；缺字段时跳过该 job 并记录 warning
- [x] 3.2 在 `cron_scheduler.py` 实现 `load_cron_yaml(path) -> list[dict]`；`start()` 中合并 YAML jobs 和 schedule_store jobs，去重（YAML 的 `id` 若与 store 冲突，store 优先）
- [x] 3.3 新建 `config/cron.example.yaml`，含注释说明各字段

## 4. server.py — 调度器生命周期

- [x] 4.1 Write failing tests: lifespan 启动时 `cron_scheduler.start()` 被调用；lifespan 关闭时 `cron_scheduler.shutdown()` 被调用
- [x] 4.2 在 `server.py` lifespan 中实例化 `CronScheduler`，lifespan 启动时调用 `start()`，yield 后调用 `shutdown()`

## 5. tools.py — schedule_task 和 cancel_task

- [x] 5.1 Write failing tests: `schedule_task` 调用 `schedule_store.create()` 并返回包含 task id 的成功消息；`cancel_task` 调用 `schedule_store.delete()` 并返回确认消息；task_id 不存在时返回错误字符串
- [x] 5.2 在 `tools.py` 添加 `schedule_task(name, cron_expr, message, timezone, user_id)`（risk_level="high"）和 `cancel_task(task_id)`（risk_level="medium"）工具

## 6. admin CLI — 调度管理命令

- [x] 6.1 Write failing tests: `list-schedules` 无任务时输出 "No scheduled tasks"；有任务时输出含 id、name、cron_expr、user_id；`add-schedule` 成功时 exit 0 并打印 task id；`remove-schedule` 成功时 exit 0；task_id 不存在时 exit 非零
- [x] 6.2 在 `admin.py` 添加 `list-schedules`、`add-schedule --name --cron --user-id --message [--agent-name] [--timezone]`、`remove-schedule --task-id` 命令

## 7. 验证

- [x] 7.1 运行完整测试套件（`uv run pytest -x -q`），确认全部通过
- [ ] 7.2 手动验证：用 `add-schedule` 创建一个每分钟触发的任务，启动服务，确认 eval trace 中出现对应 agent run 记录；用 `remove-schedule` 删除后确认不再触发
