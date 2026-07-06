# Tasks — cron-hardening

> 前置：change-1（fix-cron-store-and-once）已合并（F6.2 复用其告警助手）。每个实现 task 严格 TDD：先写测试见红 → 实现见绿。

## 1. misfire 宽限分级（F5）

- [x] 1.1 写测试：每日 cron 迟到 40min → 补跑一次；迟到 3 天 → 不 dispatch、记 `missed` history 行、next_run_at fast-forward；interval 迟到 3 天 → 仍补跑一次（`tests/integration/test_cron_poll_engine.py` 新用例）→ 见红
- [x] 1.2 实现：`_tick` due 判定加 cron 型宽限 `min(半周期, 2h)`（design D1，新增 `cron_misfire_grace` 辅助函数），超限走 claim+missed 路径 → 见绿

## 2. tick per-row 容错（F6.1）

- [x] 2.1 写测试：store 中一行 origin 为非法 JSON + 一行正常到期任务 → tick 正常触发正常行、坏行记 warning 跳过、后续 tick 不受影响；另加一行坏 cron_expr（合法 JSON 但表达式在 `compute_next_run` 处炸）验证 `_tick` 自身的 per-row 隔离 → 见红（当前 list_tasks 整批抛错 / compute_next_run 抛错终止整个 tick）
- [x] 2.2 实现：`list_tasks` 逐行 try/except 容错（跳坏行记 warning）；`_tick` 抽出 `_process_due_task` 并在调用处套 try/except（design D2）→ 见绿

## 3. 禁用必告警（F6.2）

- [x] 3.1 写测试：boot 注册遇坏行禁用时，origin 可解析 → 假 connector 收到禁用告警；告警失败不影响 boot → 见红
- [x] 3.2 实现：`start()` 禁用分支直接复用 `_deliver` 冻结文案投递（未走 `_maybe_alert_failure`——禁用是一次性终结事件，不适用其失败 streak 抑制语义）→ 见绿

## 4. fire 看门狗（F6.3）

- [x] 4.1 写测试：stub 永不返回的 fire + `fire_timeout_seconds=0.05` → 运行被取消、history 记 timeout 语义 error、`_inflight` 与信号量释放；`fire_timeout_seconds=0` → 不超时 → 见红
- [x] 4.2 实现：`SchedulingSettings.fire_timeout_seconds`（默认 900，0 需绕开既有 `or default` 落空陷阱）+ `_dispatch` 改接收完整 task dict 以便记录 timeout history + `asyncio.wait_for` 包裹（design D3）→ 见绿

## 5. tick 对齐睡眠（F7）

- [ ] 5.1 写测试：任务 3s 后到期、tick_interval=10 → 触发迟到 <1s；无任务时睡眠回落 tick_interval（可注入时钟/睡眠断言）→ 见红
- [ ] 5.2 实现：`_run_tick_loop` 睡眠 = `min(tick_interval, 距最早到期)`、下界 0.5s（design D4）→ 见绿

## 6. session 参数暴露（F6.4）

- [ ] 6.1 写测试：`schedule(action="create", session="cron/counter", ...)` → 行持久化 `session_id`；省略 → NULL；schema 含两态语义描述（`tests/integration/test_tools_schedule.py` + schema 测试）→ 见红
- [ ] 6.2 实现：工具 `session` 参数直通 facade（design D5）→ 见绿

## 7. 死代码与收尾

- [ ] 7.1 删除 `_parse_cron` 及其孤儿测试断言；`anchor` 列 docstring 标注 vestigial（design D6）
- [ ] 7.2 更新 `docs/capabilities/scheduling.md`：misfire 宽限、看门狗、session 参数、tick 对齐
- [ ] 7.3 change 收尾：`make test-pr` + `make test-integration-ci` 全绿（无新增失败）
