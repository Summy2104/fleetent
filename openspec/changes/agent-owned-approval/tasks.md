> 每个实现 task 严格 TDD：先写测试看红 → 再写实现看绿（最窄命令 `uv run pytest <file>::<test> -x -q`）。测试任务已排在对应实现任务之前。外部 HTTP（Slack/Telegram）用 respx/mock，不发真实请求；LLM mock；DB 隔离用 tmp_path/统一 fixture。

## 1. A1 — im_gateway 出站原语（Slack DM / Telegram send_message）

- [ ] 1.1 写失败测试（`tests/unit/test_im_outbound.py`）：mock Slack client，断言 `send_to(slack, user_id, text)` 先开 DM 频道再 `chat_postMessage`；mock Telegram bot，断言 `send_to(telegram, chat_id, text)` 调 `send_message`。先见红。
- [ ] 1.2 实现出站原语于 `im_gateway`（slack.py / telegram.py + 统一入口），不 `import fleetent.platform.*`。见绿。
- [ ] 1.3 写失败测试：`is_reachable(target)`——Telegram 未知 chat id 判不可达、Slack 工作区用户判可达。先见红。
- [ ] 1.4 实现可达性校验，编码平台约束。见绿。
- [ ] 1.5 写守卫测试：断言新出站模块 import 不含 `fleetent.platform.*` / `fleetent.user_store`（接入既有依赖护栏）。见绿。

## 2. A2 — 审批人路由配置（AgentFile.approval）

- [ ] 2.1 写失败测试（`tests/unit/test_agent_config_approval.py`）：`AgentFile` 解析 `approval` 块（`by_risk`、`by_tool`、`approvers`、`policy`、`on_no_approver`），默认值与 `extra="forbid"` 行为。先见红。
- [ ] 2.2 在 `agent_config.py` 增加 `ApprovalRouting` 等 pydantic 模型 + `AgentFile.approval`。见绿。
- [ ] 2.3 写失败测试：路由解析——`by_tool` 覆盖 `by_risk`；user_id 经 im-user-mapping 解析为 IM 地址；解析不到→空（触发 default-closed）。先见红。
- [ ] 2.4 实现路由解析函数（输入 risk/tool → 审批人 IM 地址列表 + policy）。见绿。

## 3. A2 — permission_gate 重构（agent 侧 store / 去 user_store / 外呼 / 不透明 actor）

- [ ] 3.1 写失败测试（`tests/integration/test_approval_store.py`）：agent 侧审批 store `ensure_schema` 自建 `approvals`、named params、CRUD；记录带正确 `session_id`（非 `""`）；模块内无 `sqlite3.connect`/`user_store._conn`。先见红。
- [ ] 3.2 实现 agent 侧审批 store（store 边界、`ensure_schema`、named params），`permission_gate` 改用它、**删除 `from fleetent.user_store import _conn, DB_PATH`**。见绿。
- [ ] 3.3 写守卫测试：`governance.permission_gate` import 不含 `fleetent.user_store` / `fleetent.platform.*`（接入依赖护栏）。先见红→实现后见绿。
- [ ] 3.4 写失败测试（`tests/unit/test_permission_gate_routing.py`）：撞门时按路由解析审批人并经 A1 出站原语外呼（mock 出站）；请求者≠审批人；回执按 `approval_id` 关联放行；actor 原样存不透明字符串、不 join users。先见红。
- [ ] 3.5 实现 `request_approval` 重构：消费路由 + A1 外呼、按 `approval_id` 关联、存不透明 actor、写正确 `session_id`。见绿。
- [ ] 3.6 写失败测试：default-closed——未解析出审批人 / 出站发送失败 / 超时，三者皆 reject；`any`（首个响应即决）/`all`（全过才放行、任一拒即拒）策略。先见红。
- [ ] 3.7 实现 default-closed 兜底 + any/all 策略。见绿。

## 4. 接线与兼容

- [ ] 4.1 写失败测试：`runtime/loop.py` 门调用接入新路由（`permission_gate_enabled=False` 仍整体跳过）；medium/high 均从 `approval` 解析审批人，解析不到按 `on_no_approver`（default reject）——断言**无"请求者本人确认"回落**。先见红。
- [ ] 4.2 实现 loop 接线。见绿。
- [ ] 4.3 写失败测试（`tests/integration/`）：单机 agent（无 platform、管理库不存在）端到端跑通一次审批（mock 出站 + resolve 走 `/approvals/{id}/resolve`）。先见红→实现后见绿。

## 5. 收尾验证

- [ ] 5.1 单层收尾：`uv run pytest tests/unit -q` 与 `uv run pytest tests/integration -q` 对照 main 基线，确认无新增失败。
- [ ] 5.2 `uv run python scripts/check_test_layers.py`（新增 unit/integration 测试层边界）通过。
- [ ] 5.3 `make test-pr` 全绿（unit〔除 quarantine〕+ 层边界 + 改动文件 ruff format/lint）。
- [ ] 5.4 `openspec validate agent-owned-approval` 通过。
- [ ] 5.5 复核：本变更未引入 `import fleetent.platform.*`；审批可在无 platform 下工作（解耦护栏）。
