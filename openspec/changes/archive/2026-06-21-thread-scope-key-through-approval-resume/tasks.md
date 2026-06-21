# Tasks

> 每个实现 task 严格 TDD：先写测试跑最窄命令**见红** → 写实现**见绿** → 可选 refactor。
> 测试任务排在对应实现任务之前。基线对照 main（门禁判据＝无新增失败）。
> 最窄命令：`uv run pytest tests/unit/test_normalizer_approval_resume.py -x -q`

## 1. 前置核实（不改产线代码，定 scope）

- [x] 1.1 复读 `normalizer.py:_resume_pending_in_session`（~330-440）确认 tool_context 在 391 构建、439 经 `resume_pending_approval(tool_context=...)` 透传执行；确认 `agent_loop` 已在函数内 import
- [x] 1.2 确认 `_resolve_scope_key` 仅 `loop.py` 内部 2 处用、无测试 patch、无外部引用（可安全改名）

## 2. resolve_scope_key 提升为公开（TDD：红 → 绿）

- [x] 2.1 **测试先行**：`tests/unit/test_normalizer_approval_resume.py` 加 `test_resolve_scope_key_is_public`——`from fleetent.runtime import loop`，断言 `hasattr(loop, "resolve_scope_key")` 且 `loop.resolve_scope_key("s", "a")` 返回非空。跑最窄命令 **见红**（属性不存在）
- [x] 2.2 **实现**：`runtime/loop.py` 把 `_resolve_scope_key` 改名为公开 `resolve_scope_key`，更新两处内部调用（~1746、~2283）。跑 2.1 **见绿**

## 3. resume tool_context 接线 scope_key（TDD：红 → 绿）

- [x] 3.1 **测试先行**：加 `test_resumed_tool_context_carries_scope_key`——用 `_resume_env`，`monkeypatch.setattr(agent_loop, "resolve_scope_key", lambda sid, an: f"SK::{sid}")`，`await normalizer.route(_msg("approve abcd1234"))` 后断言 `resume.await_args.kwargs["tool_context"].scope_key == "SK::slack:dm:U_REQ:1.1"`。跑最窄命令 **见红**（现状 scope_key=None）
- [x] 3.2 **实现**：`normalizer.py:391` 的 ToolContext 增加 `scope_key=agent_loop.resolve_scope_key(session_id, agent.name if agent else None)`。跑 3.1 **见绿**

## 4. 回归 + lint

- [x] 4.1 整文件回归：`uv run pytest tests/unit/test_normalizer_approval_resume.py tests/unit/test_loop_approval_suspend.py -q` 全绿
- [x] 4.2 `uv run ruff check` + `ruff format --check` 受影响文件（normalizer.py / loop.py / 测试）通过

## 5. spec 同步

- [x] 5.1 确认 `specs/approval-suspend-resume/spec.md` 的 MODIFIED 要求与实现一致（resume 注入的 tool_context 携带 workspace scope key，使 `/workspace` 翻译 + `/exchange` 登记对审批恢复执行的工具生效），含对应 scenario

## 6. 收尾验证

- [x] 6.1 `make test-pr`：3238 passed，仅 1 个预先存在且无关失败 `test_config.py::test_observability_logging_defaults`（环境断言，不涉本改动）——符合「无新增失败」判据
- [x] 6.2 模块边界自检：`PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` 通过；确认无 `fleetent.platform.*` 反向 import、im_gateway 仅调 runtime 公开 API
- [x] 6.3 回归确认（人读）：审批挂起/恢复其它行为（地址重建、ledger 共享、reject 路径）未变；正常回合 scope_key 解析未变（仅改名）；仅新增「resume tool_context 带 scope_key」
