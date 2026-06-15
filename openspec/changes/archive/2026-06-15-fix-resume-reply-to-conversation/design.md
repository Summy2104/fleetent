## Context

`loop.run(reply_func=...)` 只用 reply_func 投递审批 prompt（gate）；**最终回复是 run 的返回值**，由调用方投递（正常入站路径用 `msg.reply_func`，对正常消息而言即正确对话投递器）。

resume 的 `_resume_pending_in_session` 已从持久化 `address` 重建 `reply_func = make_replier(connectors, addr)`（line 366；无地址回退 `msg.reply_func` + warning）并传给续跑 loop.run。但最终回复返回后由调用方投递：
- 文本 approve：`normalizer.route` → `await msg.reply_func(reply)`，`msg` 是 **approve 命令消息**（顶层 DM / 频道里被 @ 的那条），其 reply_func 投到触发处。
- 按钮 approve：`slack.py` → `_reply(reply)`，投到**按钮所在频道顶层**（`chat_postMessage(channel=...)` 无 thread_ts）。

故最终回复脱离持久化地址：频道→顶层、私信→新会话。工具投递（send_im_message 回当前对话）与审批 prompt（地址版 reply_func）本就正确，只有最终回复用错了投递器。

## Goals / Non-Goals

**Goals:**
- 续跑最终回复（含 📬 回执）回到持久化对话地址：频道→原 thread、私信→原 DM。
- 单一收敛点 `_resume_pending_in_session` 拥有最终回复投递（它持有正确地址），消除两个调用方各自用错投递器。
- 保留无地址升级期条目的降级语义（回退触发处 + warning）。

**Non-Goals:**
- 不改 loop.run 的「最终回复为返回值、调用方投递」总体约定（仅在 resume 这一收敛点内部完成投递）。
- 不改回执渲染（#265）、审批触发面、风险分级。
- 不改正常入站路径的投递。

## Decisions

1. **`_resume_pending_in_session` 内部投递最终回复**：`reply = await resume_pending_approval(...)` + save 之后，`if reply: await reply_func(reply)`，其中 `reply_func` 是已解析的地址版（或无地址回退版）。仍 `return reply`（供日志/测试），但投递职责归本函数。
2. **调用方停止二次 post**：`route` 文本 approve 分支与 `slack.py` 按钮分支删除对返回值的再投递；保留各自的「未找到/未授权」即时提示（那是 resolve 失败、与 resume 无关的路径，仍用 msg.reply_func）。
3. 降级：无地址时 `reply_func == msg.reply_func`（既有回退），故 `_resume` 内投递仍走触发处——与旧行为等价，不回归升级期条目。
4. **TDD**：integration 红测——seed 带频道-thread 地址的 pending，直接调 `_resume_pending_in_session`（触发 msg 为顶层 DM、reply_func 为独立 mock），断言最终回复经 `send_to` 投到 `C_THREAD`+`thread=170.5`、且触发处 `msg.reply_func` 未被用于该回复。

## Risks / Trade-offs

- **双投递回归风险**：必须确保调用方不再 post，否则重复。已在两个调用方各删一处，并由「触发处 reply_func 未被用于最终回复」断言守护。
- **best-effort 投递**：地址版 reply_func（make_replier）连接器缺失/失败是 logged no-op，不抛——不影响 resume 完成与 save。
- 范围聚焦最终回复投递目标，单一收敛点，低风险。
