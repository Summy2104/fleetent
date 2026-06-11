## 1. normalizer 去 owner 前缀 + 删 NormalizedMessage.owner_id 字段

- [x] 1.1 写测试（unit）：构造无 owner 概念的 `NormalizedMessage`（不传 owner_id），经 `route`（mock 下游 loop）后实际使用的 `session_id == msg.session_id`（无 `owner:` 前缀）；并断言 `NormalizedMessage` 不再有 `owner_id` 字段 —— 当前带前缀/有字段 → 见红
- [x] 1.2 `normalizer.py`：删 `NormalizedMessage.owner_id` 字段；372/446 改为 `session_id = msg.session_id` —— 见绿
- [x] 1.3 该层窄命令复跑确认绿

## 2. slack/telegram adapter 去 owner_id 形参

- [x] 2.1 写测试（unit）：改写 `test_im_adapter_owner.py` → `slack.create_app("support", {...})`（两参），断言路由到的 msg 含 `agent_name`/`user_id`、**无** `owner_id` —— 当前 `create_app` 仍要 3 参 → 见红
- [x] 2.2 `slack.py`/`telegram.py`：`run()`/`create_app()` 去 `owner_id` 形参；`NormalizedMessage(...)` 去 `owner_id=`（slack 2 处 + telegram 1 处）；更新 docstring —— 见绿
- [x] 2.3 该层窄命令复跑确认绿

## 3. supervisor 去 owner_id_provider + Runner 两参 + 断 user_store import

- [x] 3.1 写测试（unit）：注入 fake runner 构造 `SlackSupervisor()`，`await start(agent)` 后断言 runner 以 `(agent_name, config)` **两参**被调；monkeypatch `user_store.admin_owner_id` 抛异常断言**不被触发**（证明 supervisor 不再解析 owner_id / 不读 users）。Telegram 同款一条 —— 当前 3 参 + 默认 admin_owner_id → 见红
- [x] 3.2 `slack_supervisor.py`/`telegram_supervisor.py`：删 `owner_id_provider` 参数 + `_owner_id_provider`；`Runner` 类型与 `_run()` 改两参 `(agent_name, config)`；删 `from fleetent import … user_store`（确认 user_store 无其它用途）—— 见绿
- [x] 3.3 该层窄命令复跑确认绿

## 4. 解耦回归保护（standalone 无 users 表启动连接器）

- [x] 4.1 解耦回归测试：`test_{slack,telegram}_supervisor.py::test_supervisor_reads_no_platform_user_store`——monkeypatch `user_store.admin_owner_id` 抛错，注入 fake runner `await start(agent)` 后断言 status 非 `error`、runner 以两参被调、`admin_owner_id` 不被触发。此测试 mock-based、不碰真实 DB，按项目分层规则归 **unit**（真实「无 users 表」端到端见 5.1 手动基线）。已见红→见绿。
- [x] 4.2 复用 2/3 实现使其转绿；并机械修复所有引用旧 API（`owner_id=` kwarg / 3 参 `create_app`/`run` / `msg.owner_id` 断言）的周边测试（12 个文件）—— 全绿（98 passed）
- [x] 4.3 grep 自查：`im_gateway/{slack,telegram}{,_supervisor}.py` 与 `normalizer.py` 代码层全无 `owner_id`（仅剩说明注释）；`im_gateway` 代码层全无 `user_store` 调用/ import；platform 侧 `im_gateway_management` 的 owner_id 概念未受影响（grep 仍在）

## 5. 收尾

- [x] 5.1 验证基线：解耦由 `test_{slack,telegram}_supervisor.py::test_supervisor_reads_no_platform_user_store` 自动覆盖（monkeypatch `admin_owner_id` 抛错，supervisor 启动连接器 status 非 error、不触发 users 读取）。真实「无 platform、无 `users` 表」`fleetent agent run` 活体验证留给重新部署 dev-intern。
- [x] 5.2 模块边界守卫 `scripts/check_module_boundaries.py` 通过（exit 0）；改动文件 ruff 全绿；`make test-pr` = 2747 passed + 1 个 pre-existing 失败（`test_config.py::test_observability_logging_defaults`，已确认 main d02bed21 同样红，非本改动引入）；`tests/integration` = 1877 passed + 1 个 pre-existing 失败（`test_pilot_readiness_admin.py`，main 同样红）。**本改动零新增失败**。
