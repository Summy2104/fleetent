# Tasks — cron-delivery-governance

> 每个实现 task 严格 TDD：先写测试见红 → 实现见绿。测试任务一律在对应实现任务之前。

## 1. half-set 投递参数拒绝

- [ ] 1.1 写测试：只给 `notify_target`（缺 `notify_platform`）→ 工具返回明确 error、不创建任务；反向同理；成对提供 → 正常创建（`tests/integration/test_tools_schedule.py` 新用例）→ 见红
- [ ] 1.2 实现：schedule 工具 create 分支组装 `deliver` 前校验成对性（design D1）→ 见绿

## 2. generate 目标可解析性校验（store 层）

- [ ] 2.1 grep 全仓「无目标 generate」创建点，如有内部合法调用改为显式 `deliver={"mode":"none"}`（design D2 前置排查）
- [ ] 2.2 写测试：store `create(task_type="generate", deliver=None, origin=None)` → `ValueError` 且不落行；`deliver={"mode":"none"}` → 放行；有 origin → 放行；action 无目标 → 放行（`tests/integration/test_schedule_store.py` 新用例）→ 见红
- [ ] 2.3 实现：`schedule_store.create` 增加 generate 目标校验（镜像 notify 校验）→ 见绿
- [ ] 2.4 写测试：工具路径把该 `ValueError` 转为含配置指引的 `error:` 文本 → 见红/见绿（如既有 except ValueError 已覆盖则确认文案）

## 3. create 回执明示投递目标

- [ ] 3.1 写测试：显式目标创建 → 回执含 `slack:C123(channel)`；origin 回落创建 → 回执写明投递回创建会话（`tests/integration/test_schedule_tool_next_fire_echo.py` 扩展）→ 见红
- [ ] 3.2 实现：create 成功回执追加目标描述（design D4，不动既有前缀文案）→ 见绿

## 4. fired run 排除 schedule 工具

- [ ] 4.1 写测试：generate fire 的 run 工具 schema 无 `schedule` 且无 outbound 工具；action fire 的 schema 无 `schedule` 但保留 outbound 工具；交互路径 schema 含 `schedule`（`tests/integration/test_cron_typed_dispatch.py` 模式）→ 见红
- [ ] 4.2 实现：`loop.run` 抑制通路参数化为排除集合；`cron_scheduler._agent_run` 按 task_type 传集合（design D3）→ 见绿
- [ ] 4.3 跑受影响层：`tests/integration/test_cron_*` 与 loop 抑制相关 unit 无新增失败

## 5. 文档与收尾

- [ ] 5.1 更新 `docs/capabilities/scheduling.md`：目标成对配置、创建期校验、回执明示、fired run 无 schedule 工具
- [ ] 5.2 change 收尾：`make test-pr` + `make test-integration-ci` 全绿（无新增失败）
- [ ] 5.3 （人工）Slack 实测：half-set 创建被拒的用户体验、回执目标显示（对照 AAA-8279 报告场景）
