## Context

`agent-owned-scheduled-tasks`（2026-06-10 归档）把定时任务移到 agent 侧后，`CronScheduler` 实例由 `agent_app._start_scheduler()` 创建并持在 app state；`schedule` 工具是普通函数，拿不到该实例，于是 create/remove/pause/resume 全部只操作 `schedule_store`。`_register` 把 task dict 捕获进闭包，`_fire` 不回读 store——store 与 APScheduler 内存 job 成为两个靠"记得同步"维系的真相源，而当前没有任何同步代码。AAA-8039 是其 create 路径的表现。

约束：store 的写入方目前只有 agent 进程内的 schedule 工具（`admin_cli/schedules.py` 已删）；`im_gateway/connector_registry.py` 已确立"进程级 current-instance 注册表"的代码惯例；`_fire` 刚加入 principal recheck（blocked/deleted 用户跳过），fire 时校验已有先例位置。

## Goals / Non-Goals

**Goals:**
- 运行期对定时任务的全部变更（create/remove/pause/resume/run_now）立即对运行中调度器生效
- 失步在结构上不可能：store 写入与 job 注册收进同一 owner 的同一方法，单一入口
- 调度器未运行时工具诚实降级（写 store + 如实告知生效时机），不误导 agent 回复
- fire 时回读 store 兜底：已删/已停任务永不错发

**Non-Goals:**
- 不做周期 resync 调和循环——当前无跨进程写入方，为不存在的场景付复杂度违反 YAGNI；fire 回读已保证"最坏不错发"，将来平台侧直写 store 时再补
- 不改 schedule_store 的 schema 与 ensure_schema 机制
- 不动 delivery / origin / session 绑定语义

## Decisions

**D1：write-through facade 而非"工具记得双调"。**
`CronScheduler` 新增 `create_task(...)` / `remove_task(id)` / `set_task_enabled(id, enabled)` / `run_now(id)`，方法内部 = store 写入 + `add_job`/`remove_job`。备选的"在工具四个 action 后各补一行 scheduler 调用"被否：那仍是双真相源靠纪律同步，新增第五个 action 时会再次静默回归。facade 把不变量（写库即注册）变成构造保证。

**D2：进程级 `current()` 句柄，照抄 connector_registry 模式。**
`cron_scheduler.current() -> CronScheduler | None`；`start()` 末尾登记、`shutdown()` 清除。测试用 `monkeypatch` 注入/清空。备选"工具上下文注入"被否：工具是无状态普通函数，注册表是本仓既有惯例（connector_registry 同日刚立）。

**D3：调度器未运行时，工具降级为 store-only + 诚实文案。**
`current()` 为 None（CLI 一次性运行、`scheduling.enabled=false`）时：create 仍写 store，返回值明确说明「已保存，将在 agent 服务运行后生效」；remove/pause/resume 操作 store 并注明同样语义。这同时治了 AAA-8039 截图里 agent 瞎编「环境不支持」的问题——工具结果给足事实，模型不必猜。

**D4：fire 时回读 store（与 principal recheck 并列的第二道闸）。**
`_fire` 开头按 `task["id"]` 回读：行不存在或 `enabled=0` → log warning + 卸载该 job + return。即使将来出现绕过 facade 的写入方，最坏结果是"该触发的等下次注册"，永不错发。回读后的行作为执行依据（替换闭包捕获的旧 dict），顺带修掉"task 内容更新不生效"的潜在坑。

**D5：once 任务 fire 成功后标记完成。**
置 `enabled=0`、`last_status="completed"`。与 spec 既有场景「fires once ... then marked completed」对齐；配合 D4，重启后 boot 加载也不会重 fire（现靠 misfire grace 兜，改后语义显式）。

## Risks / Trade-offs

- [facade 后 schedule_store 仍是公开模块，绕过入口直写仍可能] → 依赖护栏测试禁止 `tools/` import `schedule_store`；D4 保证绕过者最坏不错发；store docstring 标注"经 CronScheduler 变更"
- [`current()` 是进程级可变状态] → 与 connector_registry 同等定位：单 agent 单进程运行时句柄，start/shutdown 生命周期对称，测试可 monkeypatch；不是被禁的"模块级路径常量"类全局
- [fire 回读给每次触发加一次 SQLite 读] → 触发频率为分钟级人类任务，单行主键查询可忽略
- [pause 实现为 remove_job、resume 为 add_job，APScheduler 无原生 pause 状态持久化] → 以 store `enabled` 为真相，job 注册状态是其投影，语义一致
