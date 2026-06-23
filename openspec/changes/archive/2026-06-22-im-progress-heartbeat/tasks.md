## 1. core loop 心跳(helper + 间隔常量 + owner-task 包裹)

- [x] 1.1 写测试(unit, asyncio)：`_progress_heartbeat(progress_func, interval)` 协程——用极小 interval 驱动数次，断言每次以 `{"type":"heartbeat","elapsed_s":<int>=0}` 调 progress_func 且 elapsed_s 递增；progress_func 抛异常被吞、循环继续；可被 cancel —— 见红
- [x] 1.2 实现 `_HEARTBEAT_INTERVAL_S = 4.0`(模块级)+ `_progress_heartbeat` 协程(sleep→发 heartbeat→try/except 吞 progress 异常) —— 见绿
- [x] 1.3 写测试(unit, asyncio)：`_heartbeat_during(progress_func, is_sub_agent=...)` async 上下文管理器——eligible(非 sub_agent + progress_func 非 None)时 enter 起 task、退出 cancel 无残留(进入后小睡有 heartbeat 事件，退出后不再增长)；progress_func=None 或 is_sub_agent=True 时不起 task、零事件 —— 见红
- [x] 1.4 实现 `_heartbeat_during`(asynccontextmanager：enter 按守卫 create_task，finally cancel + suppress CancelledError) —— 见绿
- [x] 1.5 写测试(unit)：`_run_inner` 顶层 run 体被 `_heartbeat_during` 包裹（断言其在 run 路径被进入/带正确守卫参数；可 patch `_heartbeat_during` 验证调用与 is_sub_agent 透传）—— 见红
- [x] 1.6 实现：在 `_run_inner` 用 `async with _heartbeat_during(progress_func, is_sub_agent=is_sub_agent):` 包裹主循环体 —— 见绿

## 2. Slack 心跳分支(保活 + 耗时，记忆上次文案)

- [x] 2.1 写测试(unit)：Slack 状态文案逻辑——`tool_call` 事件更新「上次文案」；`heartbeat(elapsed_s=N)` 产出「`<上次文案> · 已 Ns`」；心跳先到(无工具)产出「🤔 思考中... · 已 Ns」；两类事件不互相清空 —— 见红
- [x] 2.2 实现：在 `slack.py` 引入每会话「上次工具文案」holder + `heartbeat` 分支，progress 处理据 type 分发，setStatus 重发保活文案(+ loading_messages) —— 见绿

## 3. Telegram 心跳 → typing 确认

- [x] 3.1 写测试(unit)：Telegram progress 路径对 `heartbeat` 事件调用 `send_chat_action(action="typing")`(用 stub bot 驱动 progress_func / 或抽出的小 helper) —— 见红
- [x] 3.2 实现/确认：确保 `telegram.py` progress 对 `heartbeat` 事件发 typing(现状对任意事件即发；如不可测则抽出最小 helper 使其可测)，无新增分支逻辑 —— 见绿

## 4. 集成、隔离校验与收尾

- [x] 4.1 写/跑集成测试(integration, asyncio)：用极小 `_HEARTBEAT_INTERVAL_S` 跑一段「有静默期」的流程，捕获 progress_func 收到的事件序列中含多次 `heartbeat` 且 elapsed_s 递增；run 结束后心跳 task 已停 —— 见红→见绿
- [x] 4.2 跑模块边界护栏 `scripts/check_module_boundaries.py` + `test_module_dependency_guardrails.py`：确认 `runtime/`、`im_gateway/` 无新增 `import fleetent.platform.*`；确认无新增模块级 AsyncExitStack/活资源单例(护栏)
- [x] 4.3 收尾门禁：`make test-pr` 全绿 + `uv run pytest tests/integration -q`(对照 main 基线无新增失败) + `uv run ruff check`(改动文件干净)
