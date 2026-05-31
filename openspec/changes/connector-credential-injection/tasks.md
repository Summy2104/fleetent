## 1. 前置核实（实现前的事实确认，无代码改动）

- [ ] 1.1 核实 `tool_registry._build_schema`（行 85-101）是否已排除 keyword-only 参数：用临时断言 / REPL 检查 `def t(q, *, client)` 的 schema 是否含 `client`。确定 D4 是否需补过滤
- [ ] 1.2 核实 `dispatch` 现有调用点（`agent_loop._safe_dispatch` 行 66、`sub_agent`、各测试）传参形态，确认新增末位 kw `user_id=None` 向后兼容、需补传的调用点清单
- [ ] 1.3 确认 `eval_logger._serialize` / `log_run` 写入的是 messages（工具 args/result），`client` 既不在 args 也不在 result——锁定「凭证不进 trace」的不变量边界

## 2. connectors 凭证接口（connectors.py）

- [ ] 2.1 Write failing tests for `Credential` / `NeedsConsent` 数据类：`tests/test_connectors.py` 断言 `Credential` 持有 `client` 且其 `repr`/`str` 屏蔽 secret（不含 secret 文本）；`NeedsConsent` 持有 `connector` 与 `consent_url`。运行 `uv run pytest -x -q` 看到红
- [ ] 2.2 Implement `Credential`、`NeedsConsent`（secret 字段 `repr=False` + 自定义 `__repr__`），看到绿
- [ ] 2.3 Write failing tests for `get_credential` + provider 缝：默认 provider 返回 `NeedsConsent`；monkeypatch provider 返回 `Credential` 时 `get_credential` 透传之；`user_id` 缺失时返回 `NeedsConsent`。看到红
- [ ] 2.4 Implement `get_credential` 委派可 monkeypatch 的模块级 `_provider`（默认返回 `NeedsConsent`），看到绿

## 3. @tool 声明 connector / scopes（tool_registry.py）

- [ ] 3.1 Write failing tests：`@tool(connector="google-drive", scopes=["drive.readonly"])` 注册后 `get_connector(name)` 返回 `("google-drive", ["drive.readonly"])`；无声明时返回 None；`get_schemas()` 输出不含 connector/scopes。看到红
- [ ] 3.2 Implement：`@tool` 新增 `connector` / `scopes` 参数，记录到模块级 `_connectors`（与 `_risk_levels` 平行）+ `get_connector()`，看到绿

## 4. keyword-only 隐藏参数不进 schema（tool_registry.py）

- [ ] 4.1 Write failing tests for `_build_schema`：`def t(query: str, *, client)` 的 schema `properties` 只含 `query`，不含 `client`；`required` 不含 `client`。看到红（依 1.1 结论；若现状已排除则改为补强守卫测试，仍须先红）
- [ ] 4.2 Implement：`_build_schema` 跳过 keyword-only 参数（`param.kind == KEYWORD_ONLY`），看到绿

## 5. dispatch 注入 Credential 的 client（tool_registry.py）

- [ ] 5.1 Write failing tests（monkeypatch `connectors.get_credential` 返回带 fake client 的 `Credential`）：声明 connector 的工具被以隐藏 `client` 注入执行并返回结果；无 connector 声明的工具不触发 `get_credential`、行为不变。看到红
- [ ] 5.2 Implement：`dispatch` 新增末位 kw `user_id=None`；访问控制后查 `get_connector`，有 connector 则 `get_credential` 返回 `Credential` 时 `fn(**kwargs, client=cred.client)`，看到绿

## 6. dispatch 未授权短路（tool_registry.py）

- [ ] 6.1 Write failing tests（monkeypatch `get_credential` 返回 `NeedsConsent`）：声明 connector 的工具不被调用（fake 工具断言未执行），dispatch 返回含 consent URL 的提示串。看到红
- [ ] 6.2 Implement：`get_credential` 返回 `NeedsConsent` 时短路、返回含 `consent_url` 的提示串，不调用工具函数，看到绿

## 7. 凭证不泄漏（守卫）

- [ ] 7.1 Write failing tests：注入 `client` 执行后，dispatch 返回值不含 secret；`Credential` 注入过程 / 工具异常的错误文本不含 secret；模拟把 dispatch 结果 + args 经 `eval_logger._serialize` 序列化后不含 secret。看到红
- [ ] 7.2 Implement：确保 `client` 不写回 `kwargs`、不进返回值；异常文本不含凭证（必要时归一化错误消息），看到绿

## 8. dispatch 调用点接入 user_id（agent_loop.py）

- [ ] 8.1 Write failing tests：`_safe_dispatch` 把 `user_id` 透传到 `dispatch`（断言 dispatch 收到 user_id）。看到红
- [ ] 8.2 Implement：`agent_loop._safe_dispatch` 及其调用处补传 `user_id`，看到绿

## 9. 收尾

- [ ] 9.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`），确认无回归
- [ ] 9.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿；`uv run mypy src` 不新增错误模式
- [ ] 9.3 更新 `docs/capabilities/tools.md`：将「connector 注入接通」从 `[ ]` 规划项标记为已实现（✅），并校正 `connectors` vs `im_connector_*` 的命名说明
- [ ] 9.4 加回归守卫 `test_no_credential_in_trace`：声明 connector 的工具一次完整 dispatch + trace 序列化，断言全链路无 secret 文本
