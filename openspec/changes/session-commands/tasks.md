# Tasks

> TDD Hard Gate:每个实现 task 前先写测试见红,再写实现见绿。测试任务排在对应实现任务之前。
> 分层:分发器纯逻辑 + 命令处理(mock session/usage)归 unit;入口接线(normalizer/dispatch)按既有 run_stream/route 单测约定归 unit(mock LLM/DB)。

## 1. 共享命令分发器骨架

- [ ] 1.1 写测试(unit):`handle_command(ctx, text)` —— 非命令返回 `None`;`/user` 经分发器仍追加并回执;会话型命令在 `ctx.session_id is None` 时返回「无会话」提示不抛异常;`ctx.session_id is None` 时 `/user` 仍可用。
- [ ] 1.2 实现 `runtime/commands.py`:`CommandContext` dataclass + 注册表 + `async handle_command(ctx, text) -> str | None`;接入 `/user`(调用 `user_instructions.handle_user_command`);会话型命令的 None-session 守卫。

## 2. /clear

- [ ] 2.1 写测试(unit):`/clear` 在 `session_lock` 下清空当前 session(mock manager.clear / session_lock),返回回执;空会话幂等。
- [ ] 2.2 实现 `/clear` handler:复用 `session.manager.clear(session_id)`,回执标明影响范围为当前会话。

## 3. /compact

- [ ] 3.1 写测试(unit):`/compact` 持锁 load→`maybe_compress(force=True)`→save(mock 三者),回执含压缩前后消息数/token 变化。
- [ ] 3.2 实现 `/compact` handler:`session_lock` 内 load、`context.maybe_compress(msgs, force=True, session_id, user_id, agent_name)`、save,生成变化回执。

## 4. /context

- [ ] 4.1 写测试(unit):`/context` 加载会话 + `estimate_tokens`,回执含消息数 + token 估算 + 占上限百分比;只读不改会话。
- [ ] 4.2 实现 `/context` handler:load + `context.estimate_tokens`,读 max_tokens 计算占比。

## 5. /usage 与 /cost

- [ ] 5.1 写测试(unit):`/usage` 调 `get_usage_summary(UsageQuery(session_id=...))`(mock),回执含 run 数 + prompt/completion/total tokens。
- [ ] 5.2 实现 `/usage` handler。
- [ ] 5.3 写测试(unit):`/cost` 以 token/预算口径回执(mock usage + budget),文案标明非美元;budget 未配置时仅报 token 总量。
- [ ] 5.4 实现 `/cost` handler(token 总量 + 预算上限/占比,显式 token 口径声明)。

## 6. 入口接线:IM(Slack / Telegram)

- [ ] 6.1 写测试(unit,route() mock):授权用户 `/clear` 等在访问门后被 `handle_command` 拦截、回执、不跑 loop;未授权用户被门挡住、命令不执行;普通消息照常进 loop。
- [ ] 6.2 实现:`normalizer.route` 把现有 `/user` 拦截点替换为统一 `handle_command(ctx, _strip_leading_mention(text))` 调用(位置不变:审批后、access gate 后、loop 前);构造 `CommandContext(agent.name, session_id, user_id)`。

## 7. 入口接线:TUI

- [ ] 7.1 写测试(unit):`tui/dispatch` 收到命令(经 `METHOD_USER` 或扩展为通用 `METHOD_COMMAND`)在服务端调用 `handle_command`(ctx 取 `Connection.agent_name` + `session_id` + `user_id`),返回回执;客户端 `KNOWN_COMMANDS`/`parse_command` 识别新命令名。
- [ ] 7.2 实现:`tui/commands.py` `KNOWN_COMMANDS` 增加 clear/compact/context/usage/cost;`tui/protocol.py` + `tui/dispatch.py` 用通用命令方法调用 `handle_command`;`tui/backend.py` + `tui/app.py` 客户端分支 + `/help` 文案。

## 8. 收尾

- [ ] 8.1 跑 `make test-pr`(unit + 层边界 + 改动文件 ruff)全绿。
- [ ] 8.2 跑 `uv run pytest tests/integration -q` 对照 main 基线,无新增失败。
- [ ] 8.3 `ruff format` + `ruff check` + `mypy`(改动文件)无新增问题。
