> 前置依赖：热修 change `fix-cron-fire-outbound-connectors`（fired run 注入 `outbound_connectors`，修 AAA-8039）已合入 main。

## 1. schema：scheduled_tasks 分型列

- [ ] 1.1 写测试（integration）：以新版 `AGENT_STATE_MIGRATIONS` 打开旧版 `agent_state.db` → `task_type`/`notify_text` 列存在、既有行 `task_type='generate'`；全新库同样成立 —— 见红
- [ ] 1.2 `runtime/agent_state_migrations.py` 追加一版（两条 `ALTER TABLE ... ADD COLUMN`）—— 见绿
- [ ] 1.3 该层窄命令复跑确认绿

## 2. schedule_store：携带与校验新字段

- [ ] 2.1 写测试（integration）：`create(task_type="notify", notify_text=...)` 入库可读回；`notify` 缺 `notify_text` → 校验错误；`generate`/`action` 缺 `message` → 校验错误；不传 `task_type` → 默认 `generate` —— 见红
- [ ] 2.2 `schedule_store.create/list_tasks` 增列与按型校验 —— 见绿
- [ ] 2.3 该层窄命令复跑确认绿

## 3. notify 型触发：调度器直发、零 agent

- [ ] 3.1 写测试（unit）：monkeypatch `agent_loop.run` 抛 AssertionError + fake connector；notify 任务 `_fire` → `outbound.send_to` 收到 `notify_text` 原样、`agent_loop.run` 未被触发；投递失败 → `last_status="error"` —— 见红
- [ ] 3.2 `cron_scheduler._fire` 按 `task_type` 分流，notify 走直发路径 —— 见绿
- [ ] 3.3 该层窄命令复跑确认绿

## 4. generate 型触发：运行声明 + 契约投递

- [ ] 4.1 写测试（unit）：捕获 `loop.run` kwargs/messages → 消息序列含定时任务声明（含目标、`[SILENT]` 说明、"没有对话对象"）；回复经 `_deliver` 投递；`[SILENT]` 回复跳过投递 —— 见红
- [ ] 4.2 实现声明注入（generate 分支）；`_deliver` 行为保持 —— 见绿
- [ ] 4.3 该层窄命令复跑确认绿

## 5. action 型触发：不广播，仅记录

- [ ] 5.1 写测试（unit）：action 任务 fire → `_deliver` 不投递到目标；回复进 `_record_run`/trace；run 抛错 → `last_status="error"` —— 见红
- [ ] 5.2 实现 action 分支（短路广播）—— 见绿
- [ ] 5.3 该层窄命令复跑确认绿

## 6. schedule 工具：分型创建 + 创建时定稿指引

- [ ] 6.1 写测试（unit）：`schedule(action="create", task_type="notify", notify_text=...)` 创建成功返 id；notify 缺文案 → 错误字符串不抛异常；无 `task_type` 旧调用形状 → `generate`；工具 schema/描述含判定问题与定稿流程 —— 见红
- [ ] 6.2 `tools/builtin_tools.py` schedule 工具增参、校验与描述 —— 见绿
- [ ] 6.3 该层窄命令复跑确认绿

## 7. 状态语义（意图级）

- [ ] 7.1 写测试（integration）：三型各一条意图失败路径（notify 投递失败 / generate run 失败与投递失败 / action run 失败）→ `last_status="error"` 且 `last_error` 含因 —— 见红
- [ ] 7.2 `_record_run` 调用点按型传入意图级结果 —— 见绿
- [ ] 7.3 该层窄命令复跑确认绿

## 8. 收尾

- [ ] 8.1 文档同步：`docs/architecture/data-model.md` scheduled_tasks 列清单补 `task_type`/`notify_text`
- [ ] 8.2 验证基线：无 platform 环境下三型任务创建/触发全通（守住 agent-owned 无 platform 依赖）；`make test-pr` 全绿 + `uv run pytest tests/integration -q` 对照 main 基线无新增失败
