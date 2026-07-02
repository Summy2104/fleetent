# Tasks — managed-approval-actor-identity

> 严格 TDD：先写测试跑到见红，再写实现跑到见绿；测试任务在实现任务之前。

## P0 — 审批决策人身份一致化（AAA-8266）

- [ ] 1.1 (test) unit：`tests/unit/test_approval_decision_actor.py` —
  `im_gateway/access.resolve_decision_actor`：
  - 注入 resolver（managed，`set_im_identity_resolver`）+ `("slack","U123")` → 返回内部 id（如 `uuid-x`）；
  - 未注入（standalone）→ 原样返回 `"U123"`；
  - 空/`unknown` id → 返回 None（fail closed）。
  跑该文件见红。
- [ ] 1.2 (impl) `im_gateway/access.py`：新增 `resolve_decision_actor(platform, platform_user_id, agent_name)`（薄封装 `resolve_identity`，`IMIdentityResolutionError`→None）。见绿。
- [ ] 1.3 (test) unit：`tests/unit/test_approval_button_actor_resolution.py` —
  - Slack `handle_approval_action`：mock `approval_store.get_approval`→None、`session_mgr.get_pending_approval`→None、`resolve_approval_request`→AsyncMock(True) 捕获 kwargs；注入 resolver 映射 `U123→uuid-x`；构造 body(user.id=U123)；断言 `approver_user_id=="uuid-x"`（managed）；不注入时 =="U123"（standalone）。
  - Telegram `handle_approval_callback`：同构（`cq.from_user.id`），断言解析后 id。
  跑该文件见红。
- [ ] 1.4 (impl) `im_gateway/slack.py::handle_approval_action` + `im_gateway/telegram.py::handle_approval_callback`：判权前 `resolve_decision_actor(...)`；None→fail-closed 走原"无权审批"提示；`approver_user_id=` 用解析后 id；展示仍用原始 clicker。见绿。

## P1 — 物化不再静默降级（AAA-8267 立即项）

- [ ] 2.1 (test) unit：`tests/unit/test_apply_overrides_logs_on_invalid.py` —
  `materialize._apply_overrides(base, {"models":{"targets":[],"routes":{"vision":[{"target":"vision-model"}]}}})`：断言返回 base（im 等被丢）**且** `caplog` 出现 `agent_override_validation_failed` ERROR（含 agent 名）。跑该文件见红。
- [ ] 2.2 (impl) `platform/agent_lifecycle/materialize.py::_apply_overrides`：`except` 分支加 `_logger.error("agent_override_validation_failed", agent=base.name, error=str(exc))`，仍 `return base`。见绿。

## 收尾

- [ ] 3.1 层/模块边界：`check_test_layers.py` + `check_module_boundaries.py` 通过；agent→platform 护栏 `test_module_dependency_guardrails.py` 绿。
- [ ] 3.2 门禁：`make test-pr` + `make test-integration-ci` 无新增失败。
- [ ] 3.3 mypy：改动文件对照 baseline 无新增报错。
