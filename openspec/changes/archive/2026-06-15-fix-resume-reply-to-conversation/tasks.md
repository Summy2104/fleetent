## 1. 续跑最终回复回到持久化对话

- [x] 1.1 写测试（红）：seed 带频道-thread 地址的 pending，直接调 `_resume_pending_in_session`（触发 msg 顶层 DM、reply_func 独立 mock），断言最终回复经 `send_to` 投到 `C_THREAD`+`thread=170.5`、触发处 `msg.reply_func` 未被用于该回复
- [x] 1.2 实现（绿）：`normalizer._resume_pending_in_session` 末尾 `if reply: await reply_func(reply)`（地址版/回退版），仍返回 reply
- [x] 1.3 实现（绿）：`normalizer.route` 文本-approve 分支删除 `await msg.reply_func(reply)`（不二次 post）
- [x] 1.4 实现（绿）：`slack.py` 按钮分支删除 `await _reply(reply)`（不二次 post）

## 2. 回归保护

- [x] 2.1 既有无地址降级用例（`test_resume_missing_address_degrades_with_warning`）仍通过：回退触发处 + warning
- [x] 2.2 `test_normalizer_approval_resume`（无地址 fallback 下 `msg.reply_func` 仍被 await）仍通过

## 3. 收尾验证

- [x] 3.1 受影响层单测/集成全绿（normalizer / slack approval / resume-address）
- [x] 3.2 `make test-pr` 全绿（无新增失败）
- [x] 3.3 `uv run pytest tests/integration -q` 对照 main 基线无新增失败
- [x] 3.4 `openspec validate fix-resume-reply-to-conversation --strict` 通过
- [x] 3.5 `uv run mypy src` 无新增错误；改动文件 ruff 净
- [ ] 3.6 Slack 实测：频道审批后回执回原 thread；私信审批后回执回原 DM
