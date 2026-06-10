## 1. CronScheduler facade + current() 句柄

- [x] 1.1 Write failing tests for facade & current(): `tests/integration/test_cron_scheduler.py` 新增——①`create_task` 后 `get_job(id)` 非 None 且 store 有行；②`remove_task` 后 job 与行均消失；③`set_task_enabled(False/True)` 先卸载再重注册；④`start()` 后 `current()` 返回实例、`shutdown()` 后返回 None。最窄命令见红
- [x] 1.2 Implement facade & current() to pass tests: `cron_scheduler.py` 新增 `create_task`/`remove_task`/`set_task_enabled`/`run_now` 公开方法（store 写入 + add_job/remove_job 同方法内完成）与模块级 `current()` 句柄（start 登记 / shutdown 清除）。同一命令见绿

## 2. fire 时回读校验 + once 完成标记

- [x] 2.1 Write failing tests for fire-time revalidation: ①行被绕过 facade 删除后 job 触发 → 跳过执行、warning、job 卸载；②`enabled=0` 同理；③once 任务 fire 成功后 `enabled=0` + `last_status="completed"`，重启 boot 不再注册。最窄命令见红
- [x] 2.2 Implement fire-time revalidation to pass tests: `_fire` 开头按 id 回读 store（缺行/disabled → log + 卸载 + return），回读行替换闭包捕获 dict 作为执行依据；once 成功后写完成标记。同一命令见绿

## 3. schedule 工具改走 facade + 诚实降级

- [x] 3.1 Write failing tests for tool-through-facade: `tests/integration/test_tools_schedule.py` 新增——①scheduler 运行时 `schedule(action="create")` 后 job 立即注册；②remove/pause/resume 同步生效；③`current()` 为 None 时 create 仍落库且返回文案含「将在 agent 服务运行后生效」语义、不声称已激活；④依赖护栏：`tools/` 下任何模块不 import `fleetent.schedule_store`。最窄命令见红
- [x] 3.2 Implement tool refactor to pass tests: `builtin_tools.schedule` 全部 action 经 `cron_scheduler.current()` facade；无实例时走 store-only 降级分支并返回诚实文案；`run_now` 改走公开方法、删除对私有 `_fire` 的调用。同一命令见绿

## 4. 收尾

- [x] 4.1 `make test-pr` 全绿；`uv run pytest tests/integration -q`（不带 `-x`）对照 main 基线无新增失败
- [ ] 4.2 本地真实验证：重装/重启 my-bot，Slack 复现 AAA-8039 场景（「两分钟后给我发一个通知」），确认到点真实送达
