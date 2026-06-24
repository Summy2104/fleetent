## 1. 创建期 footgun 护栏

- [x] 1.1 写测试(integration, 注入 agent_state.db):`create(task_type="generate", deliver=None, message="把结果私信发送给 U1")` → 抛 `ValueError`(文案含纠正引导)—— 见红
- [x] 1.2 写测试:不触发的情形通过——(a) generate + 配了 `deliver` + message 含发送祈使;(b) generate + 无 deliver + message 不含发送祈使;(c) `task_type="action"` + message 含发送祈使 —— 见红
- [x] 1.3 实现:`schedule_store` 加发送祈使正则 + 在 per-type 校验后加护栏(generate ∧ deliver is None ∧ message 命中 → ValueError 引导文案)—— 见绿

## 2. schedule 工具引导

- [x] 2.1 在 `schedule` 工具 docstring / message 参数说明补充「投递用 notify_target 配置、不写进 message;generate 不自发、action 才自发」

## 3. 收尾门禁

- [x] 3.1 跑既有 `test_schedule_store*` / `test_builtin_schedule_tool*` 确认无回归
- [x] 3.2 `make test-pr` 全绿;改动文件 `ruff check` 干净
