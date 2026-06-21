# Tasks

> 每个实现 task 严格 TDD：先写测试跑最窄命令**见红** → 写实现**见绿**。
> 测试任务排在对应实现任务之前。基线对照 main（门禁判据＝无新增失败）。
> 最窄命令：`uv run pytest tests/unit/test_slack_assistant.py -x -q`

## 1. 前置核实

- [ ] 1.1 复读 slack.py 三处回复路径（`_make_status_funcs.reply_func` ~131-141 / 审批 `_reply` ~228-232 / mention `reply_func` ~434-440）与 `normalizer.py:725` 无条件 `reply_func(response)`；确认 `_make_status_funcs(client, channel, reply_thread, say)` 可直接构造

## 2. _has_postable_content + 守卫接线（TDD：红 → 绿）

- [ ] 2.1 **测试先行**：`tests/unit/test_slack_assistant.py` 加：
  - `test_has_postable_content`：`("",None)`/`("  ",None)`/`("\n",None)` → False；`("hi",None)`/`("",[{"type":"section"}])` → True
  - `test_make_status_funcs_skips_empty_reply`：构造 `_make_status_funcs(client=MagicMock(assistant_threads_setStatus=AsyncMock()), channel="C", reply_thread="t", say=AsyncMock())`，取 reply_func；`await reply_func("")` 后断言 `say.assert_not_awaited()`
  - `test_make_status_funcs_posts_nonempty`：同上 `await reply_func("hi")` 后 `say.assert_awaited()`；`await reply_func("", blocks=[{"type":"section"}])` 后 `say.assert_awaited()`
  跑最窄命令 **见红**（现状空文本会调 say → 断言 not_awaited 失败）
- [ ] 2.2 **实现**：slack.py 加模块级 `_has_postable_content(text, blocks)`；三处回复路径在状态清除后、Slack 调用前用它短路（path 1 改 `if say is not None and _has_postable_content(text, blocks)`；path 2/3 加 `if not _has_postable_content(text, blocks): return`）。跑 2.1 **见绿**

## 3. 回归 + lint

- [ ] 3.1 整文件回归：`uv run pytest tests/unit/test_slack_assistant.py -q` 全绿（含既有 `test_assistant_reply_clears_status_and_says` 非空投递不回归）
- [ ] 3.2 `uv run ruff check` + `ruff format --check` `src/fleetent/im_gateway/slack.py` + 测试 通过

## 4. spec 同步

- [ ] 4.1 确认 `specs/im-gateway/spec.md` 新增「空回复不投递」要求与实现一致（空文本+无 blocks 跳过；blocks-only 仍投递），含对应 scenario

## 5. 收尾验证

- [ ] 5.1 `make test-pr`：全绿或仅预先存在且无关失败（判据＝无新增失败）
- [ ] 5.2 模块边界自检通过；无 `fleetent.platform.*` 反向 import
- [ ] 5.3 回归确认（人读）：线程优先、状态指示、非空/ blocks-only 投递均未变；仅新增「空内容跳过投递」
