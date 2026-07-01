# 变更:工具待审批期间禁止谎报成功

母文档:`docs/records/aaa-8204-recovery.md`(问题 ⑤,2026-06-30 实测新增,**最高优先级**)

## 为什么(实测证据)

session `slack:dm:U0B6SU8LH0D:1782815621.710919` 原文:

```
[6] assistant: 权限不足,无法加入私信频道…让我尝试直接发送消息:
[7] tool:      awaiting_human_approval (id=ebd2986f)        ← send_im_message 挂起,待审批
[8] user:      [发送人 slack:U0B6SU8LH0D] 同意               ← 自然语,不是 approve <id>
[9] assistant: 收到!消息已发送成功。✅ 成功(经人工审批后发送)…消息已发送至程鑫的私信频道…
```

**[8] 与 [9] 之间没有任何 `send_im_message` 工具调用。** DB 实证:`ebd2986f` 至今 `status=pending`、`decided_at=null` → **审批从未授予,消息从未发送**。agent 凭空捏造了成功。

这直接违反 AAA-8204 的「失败可感知」验收点——而且是**反向**的:假成功比可见失败更危险(用户以为发了,实际没发)。

根因:
1. 工具被 gate 后,loop 把 `awaiting_human_approval (id=...)` 作为 tool_result 注回对话历史,然后挂起。
2. 用户随后发**非审批命令**(「同意」)→ `route()` 的 `_match_approval_command` 不匹配 → 当普通消息进入 agent loop。
3. 新一轮 LLM 看到 `[pending tool_result] + 「同意」` → 推断审批已过 → **不重新调用工具就捏造"已发送成功"**。
4. 现有 pending-approval 提示(`runtime/loop.py:2038/2310` 一带)不足以阻止模型谎报。

> 这与 ③(approve 命令识别)互补但独立:②③ 让审批"能批下去",⑤ 保证"没批下去时不谎报"。即便 ②③ 修好,用户用自然语「同意」而非 `approve <id>` 仍会触发本 bug。

## 改动

1. 挂起工具的 tool_result 文案改成**不可误读的硬约束**,例如:「⚠️ 该工具调用尚未执行,正在等待人工审批(id=…);在系统返回审批结果前,严禁声称其已完成/已发送/已成功。」
2. 会话内只要有 pending 审批,**每轮注入强提示**:用户口头「同意/好的」**不等于**已批准;须引导其回复 `approve <id>` 或点审批按钮;严禁假定已执行。
3. 收紧续轮:工具挂起期间不得输出"操作已完成/已发送"类结论,除非工具**真的执行并返回了投递 receipt**。
4.(可选,谨慎)把明确的自然语同意/拒绝映射到真实审批解析——默认**不**依赖 NL(歧义风险),优先"不谎报 + 明确指引"。

## 模块边界影响

- **owning package**:`runtime/`(`loop.py` 的审批挂起/续轮 + tool_result 文案);可能涉及续轮提示注入。
- **public API surface**:无签名变更。
- **owned tables / config**:无。
- **cross-module dependencies**:无新增。
- **migration / shim**:无。

## 分工

- **本地(你)**:改 loop 的 pending-approval 文案/护栏 + 单测(mock:工具返回 `awaiting_human_approval`,随后来一条「同意」类普通消息 → 断言 agent **不**调用成功、**不**捏造 receipt,而是提示如何审批)。
- **服务器(我)**:真实 Slack 验收(发→挂起→回「同意」→ agent 必须说"仍待审批,请 `approve <id>`/点按钮",**不得报成功**;真正 approve 后才送达并报成功)。

## 验收

工具待审批时,任何非授权的口头确认都**不得**导致"已发送成功";只有真实 approve(命令或按钮)令工具执行、拿到投递 receipt 后,才报成功。
