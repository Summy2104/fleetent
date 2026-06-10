## Why

AAA-8039 实测确认（2026-06-10，本地 my-bot 黑盒复现）：运行期通过 `schedule` 工具创建的定时任务**永不触发**。根因是工具层只调 `schedule_store` 写库，没有任何代码把变更同步给运行中的 `CronScheduler`——调度器仅在 `start()` 时加载存量任务。这是一类失步 bug，覆盖全部四个变更操作：create 永不注册、remove 后僵尸 job 继续触发、pause 无效、resume 无效（boot 时 disabled 任务本就不加载）。现行 `cron-scheduled-tasks` spec 其实已要求「activated immediately / deregister & register accordingly」，实现未兑现且测试只断言了 store 副作用。项目未上线，按结构性正确方案修：消除双写，使失步不可能发生。

## What Changes

- **CronScheduler 成为定时任务唯一变更入口（write-through facade）**：新增公开方法 `create_task` / `remove_task` / `set_task_enabled` / `run_now`，每个方法内部原子完成 store 写入 + 对应 `add_job`/`remove_job`；`schedule_store` 降级为 scheduler 的私有持久化层
- **进程级 current-scheduler 句柄**：`cron_scheduler.current()`，`start()` 登记、`shutdown()` 清除（模式同 `im_gateway/connector_registry`）
- **`schedule` 工具改走 facade**，不再直接 import `schedule_store`（依赖护栏测试钉住）；`run_now` 不再调私有 `_fire`
- **工具诚实降级**：调度器未运行（CLI 一次性运行 / scheduling disabled）时仍写 store，但工具返回值如实说明「任务已保存，将在 agent 服务运行后生效」
- **fire 时回读校验（纵深防御）**：触发时按 id 回读 store，行不存在或 `enabled=0` → 跳过执行并卸载 job（与已有的 principal recheck 并列）
- **once 任务触发后标记完成**：fire 成功后置 `enabled=0` + `last_status="completed"`，store 不残留"看似活着"的一次性任务

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `cron-scheduled-tasks`: 「schedule tool for managing scheduled tasks」requirement 升级为强制经由 CronScheduler 单一变更入口（含降级场景）；新增「Live mutation through a single owner」与「Fire-time revalidation against the store」两条 requirement（once 触发后标记完成由既有场景覆盖，本次实现兑现）

## Impact

- 受影响代码：`src/fleetent/cron_scheduler.py`（facade 方法 + current() 句柄 + fire 回读 + once 完成标记）、`src/fleetent/tools/builtin_tools.py`（schedule 工具改走 facade）、`src/fleetent/runtime/agent_app.py`（无需大改，start/shutdown 已有调用点）
- 受影响测试：`tests/integration/test_tools_schedule.py`、`tests/integration/test_cron_scheduler.py` 补 live-registration 断言；新增工具层依赖护栏（不得 import schedule_store）
- 无 schema / API / 依赖变更；纯 agent 侧，符合 agent/platform 解耦契约
- 修复对应 Jira：AAA-8039
