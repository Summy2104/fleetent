## 1. normalizer 去 owner 前缀 + 删 NormalizedMessage.owner_id 字段

- [ ] 1.1 写测试（unit）：构造无 owner 概念的 `NormalizedMessage`（不传 owner_id），经 `route`（mock 下游 loop）后实际使用的 `session_id == msg.session_id`（无 `owner:` 前缀）；并断言 `NormalizedMessage` 不再有 `owner_id` 字段 —— 当前带前缀/有字段 → 见红
- [ ] 1.2 `normalizer.py`：删 `NormalizedMessage.owner_id` 字段；372/446 改为 `session_id = msg.session_id` —— 见绿
- [ ] 1.3 该层窄命令复跑确认绿

## 2. slack/telegram adapter 去 owner_id 形参

- [ ] 2.1 写测试（unit）：改写 `test_im_adapter_owner.py` → `slack.create_app("support", {...})`（两参），断言路由到的 msg 含 `agent_name`/`user_id`、**无** `owner_id` —— 当前 `create_app` 仍要 3 参 → 见红
- [ ] 2.2 `slack.py`/`telegram.py`：`run()`/`create_app()` 去 `owner_id` 形参；`NormalizedMessage(...)` 去 `owner_id=`（slack 3 处 + telegram 1 处）；更新 docstring —— 见绿
- [ ] 2.3 该层窄命令复跑确认绿

## 3. supervisor 去 owner_id_provider + Runner 两参 + 断 user_store import

- [ ] 3.1 写测试（unit）：注入 fake runner 构造 `SlackSupervisor()`，`await start(agent)` 后断言 runner 以 `(agent_name, config)` **两参**被调；monkeypatch `user_store.admin_owner_id` 抛异常断言**不被触发**（证明 supervisor 不再解析 owner_id / 不读 users）。Telegram 同款一条 —— 当前 3 参 + 默认 admin_owner_id → 见红
- [ ] 3.2 `slack_supervisor.py`/`telegram_supervisor.py`：删 `owner_id_provider` 参数 + `_owner_id_provider`；`Runner` 类型与 `_run()` 改两参 `(agent_name, config)`；删 `from fleetent import … user_store`（确认 user_store 无其它用途）—— 见绿
- [ ] 3.3 该层窄命令复跑确认绿

## 4. 解耦回归保护（standalone 无 users 表启动连接器）

- [ ] 4.1 写测试（integration）：注入 fake runner 构造 `SlackSupervisor()` 并 `await start(agent)`，在无 `users` 表环境下断言——status 不为 `error`、无 `no such table: users` 抛出、fake runner 被两参调用成功。Telegram 同款 —— 见红（现行默认会抛 `no such table: users`）
- [ ] 4.2 复用 2/3 实现使其转绿
- [ ] 4.3 grep 自查：`im_gateway/{slack,telegram}{,_supervisor}.py` 与 `normalizer.py` 全无 `owner_id`；`im_gateway` 全无 `import … user_store`；platform 侧 `im_gateway_management` 的 owner_id 概念未受影响（grep 仍在）

## 5. 收尾

- [ ] 5.1 验证基线：「无 platform、无 `users` 表」环境下 `fleetent agent run <agent>`（声明 `connectors.slack`，env token 可解析）启动后连接器 status 非 error、日志无 `no such table: users`
- [ ] 5.2 模块边界守卫：`PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` 通过；`make test-pr` 全绿 + `uv run pytest tests/integration -q`（对照 main 基线，无新增失败）
