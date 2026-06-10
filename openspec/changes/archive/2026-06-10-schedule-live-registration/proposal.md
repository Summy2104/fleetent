## Why

AAA-8039 实测确认（2026-06-10，本地 my-bot 黑盒复现）：运行期通过 `schedule` 工具创建的定时任务**永不触发**。根因是工具层只调 `schedule_store` 写库，没有任何代码把变更同步给运行中的 `CronScheduler`——调度器仅在 `start()` 时加载存量任务。这是一类失步 bug，覆盖全部四个变更操作：create 永不注册、remove 后僵尸 job 继续触发、pause 无效、resume 无效（boot 时 disabled 任务本就不加载）。现行 `cron-scheduled-tasks` spec 其实已要求「activated immediately / deregister & register accordingly」，实现未兑现且测试只断言了 store 副作用。项目未上线，按结构性正确方案修：消除双写，使失步不可能发生。

## What Changes

- **CronScheduler 成为定时任务唯一变更入口（write-through facade）**：新增公开方法 `create_task` / `remove_task` / `set_task_enabled` / `run_now`，每个方法内部原子完成 store 写入 + 对应 `add_job`/`remove_job`；`schedule_store` 降级为 scheduler 的私有持久化层
- **进程级 current-scheduler 句柄**：`cron_scheduler.current()`，`start()` 登记、`shutdown()` 清除（模式同 `im_gateway/connector_registry`）
- **`schedule` 工具改走 facade**，不再直接 import `schedule_store`（依赖护栏测试钉住）；`run_now` 不再调私有 `_fire`
- **工具诚实降级**：调度器未运行（CLI 一次性运行 / scheduling disabled）时仍写 store，但工具返回值如实说明「任务已保存，将在 agent 服务运行后生效」
- **fire 时回读校验（纵深防御）**：触发时按 id 回读 store，行不存在或 `enabled=0` → 跳过执行并卸载 job（与已有的 principal recheck 并列）
- **once 任务触发后标记完成**：fire 成功后置 `enabled=0` + `last_status="completed"`，store 不残留"看似活着"的一次性任务
- **fire 时 principal 复检改为按域执行**（实施中实测发现的第二处断点）：identity-port 的存档复检（2026-06-10 合并）把所有 `user_id` 一律按平台用户查 `user_store`——IM 渠道担保身份（spec 自己规定不读 user_store）必然查无此人，被误判为"已删"而静默跳过，standalone 部署下**所有** IM 创建的任务死亡。改为：平台用户查到且 blocked→拒；users 表不存在（无用户管理部署）→信任存档身份；查无此人但任务带 IM origin（渠道担保）→放行；查无此人且无 IM origin→拒（平台域"删则拒"语义保留）；`system`/`default` 分别走系统主体与占位放行
- **任务属主取执行 principal**：`ToolContext` 新增 `principal` 字段（loop 注入），schedule 工具创建任务时属主取 `tool_context.principal.user_id`，不再信任模型自由填写的 `user_id` 参数（无 context 时保留参数回退）

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `cron-scheduled-tasks`: 「schedule tool for managing scheduled tasks」requirement 升级为强制经由 CronScheduler 单一变更入口（含降级场景与属主取自执行 principal）；新增「Live mutation through a single owner」与「Fire-time revalidation against the store」两条 requirement（once 触发后标记完成由既有场景覆盖，本次实现兑现）
- `identity-port`: 「非凭证身份获取路径」的③存档复检改为按身份所属域执行——平台用户经 user_store 复检（block/删→拒）；IM 渠道担保身份不经 user_store，凭任务 IM origin 放行；无用户管理部署信任存档身份

## Impact

- 受影响代码：`src/fleetent/cron_scheduler.py`（facade 方法 + current() 句柄 + fire 回读 + once 完成标记）、`src/fleetent/tools/builtin_tools.py`（schedule 工具改走 facade）、`src/fleetent/runtime/agent_app.py`（无需大改，start/shutdown 已有调用点）
- 受影响测试：`tests/integration/test_tools_schedule.py`、`tests/integration/test_cron_scheduler.py` 补 live-registration 断言；新增工具层依赖护栏（不得 import schedule_store）
- 无 schema / API / 依赖变更；纯 agent 侧，符合 agent/platform 解耦契约
- 修复对应 Jira：AAA-8039
