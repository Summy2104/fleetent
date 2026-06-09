## 1. loop.py 进度批级聚合（执行阶段发出）

- [ ] 1.1 Write failing test for batch progress: 一轮多工具时，`run()` 在批次执行前以 `{"type":"tool_call","names":[...]}` 调用 `progress_func` **恰好一次**（mock progress_func，断言 names 含全部工具、含兼容 `name=names[0]`）
- [ ] 1.2 Implement: 将进度发出从 `_plan_run_slots()` 规划期逐工具改为批次执行起点发一次聚合事件；guardrail/审批仍按原序串行；保留向后兼容 `name`
- [ ] 1.3 Write failing test: sub_agent 内工具批次不触发父 `progress_func`
- [ ] 1.4 Implement/verify sub_agent 排除逻辑通过 1.3
- [ ] 1.5 Write failing test: `progress_func` 抛异常时 run 不中断（异常被捕获并 log）
- [ ] 1.6 Implement/verify 异常隔离通过 1.5

## 2. Slack 适配器改用 Assistant 协议

- [ ] 2.1 Write failing test: 适配器经 slack-bolt `Assistant` 容器处理 assistant 会话，`setStatus` 绑定从 `assistant_thread_started` 获得的 `thread_ts`（mock client，断言用的是 assistant 线程 ts 而非 `event.ts`）
- [ ] 2.2 Implement: 重构 `slack.py` 事件层为 `Assistant` 容器（`thread_started` + `user_message`），用框架提供的 `set_status`/`say`/context 构造绑定到正确线程的 `reply_func`/`progress_func`/`upload_func`，再走 `route()`
- [ ] 2.3 Write failing test: 批级事件 `{"type":"tool_call","names":[A,B]}` 下，`setStatus` 文案聚合展示 A 与 B 两个工具（不只最后一个）
- [ ] 2.4 Implement 聚合状态文案：names→可读文案映射、拼接、超长截断
- [ ] 2.5 Write failing test: 未启用 Agents & Assistants（`setStatus` 失败）时降级——后续状态更新跳过、`reply_func` 仍经 `say()` 投递、DM 对话可用
- [ ] 2.6 Implement 降级路径 + 保留 channel `app_mention` 处理器
- [ ] 2.7 Write failing test: DM 消息不被 assistant 容器与旧 `message` 处理器**重复响应**（仅一次）；channel @mention 仍走 app_mention
- [ ] 2.8 Implement/verify 去重（收敛旧 im `message` 处理器）通过 2.7

## 3. Telegram 回归

- [ ] 3.1 Write failing/adjusted test: telegram `progress_func` 收到批级事件 `{"type":"tool_call","names":[...]}` 仍触发 `sendChatAction("typing")`，行为不退化
- [ ] 3.2 Implement/verify telegram 适配通过 3.1（忽略 names，仅触发 typing）

## 4. 收尾验证

- [ ] 4.1 受影响层：`uv run pytest tests/unit -q`（im_gateway / runtime loop 相关，无新增失败）
- [ ] 4.2 架构校验：确认 `im_gateway/`、`runtime/` 未 `import fleetent.platform.*`、未写 platform 表；agent 可在无 platform 环境 `fleetent agent run` 正常对话
- [ ] 4.3 改动文件 `uv run ruff format` + `uv run ruff check` + `uv run mypy src`
- [ ] 4.4 PR 门禁：`make test-pr` 全绿；`uv run pytest tests/integration -q` 对照 main 基线无新增失败
