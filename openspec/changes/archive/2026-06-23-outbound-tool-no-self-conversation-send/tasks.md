## 1. send_im_message 当前会话 no-op

- [x] 1.1 写测试(unit):`send_im_message` 目标=当前对话发起人(DM user)时**不调用** `outbound.send_to`、返回未投递的引导文案;目标=当前频道(channel)时同样 no-op —— 见红
- [x] 1.2 写测试(unit):目标=**第三方**用户/频道时,照常调用 `outbound.send_to` 投递(行为不变,防回归)—— 见红
- [x] 1.3 实现:在 `send_im_message` 入口处用 `approval_policy.risk_for(...)=="none"`(即当前对话)判定 → 直接返回引导文案、不投递;移除/绕过原 self-DM pin 投递路径 —— 见绿
- [x] 1.4 跑既有 `tests/unit/test_*outbound*`/`test_builtin_tools*` 等相关用例,确认无回归

## 2. 收尾门禁

- [x] 2.1 `make test-pr` 全绿(对照 main 基线无新增失败);改动文件 `ruff check` 干净
