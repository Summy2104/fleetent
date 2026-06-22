## Context

命令逻辑当前分散三处:审批在 `im_gateway/normalizer.route`(正则)、`/user` 在 `runtime/user_instructions.handle_user_command`、TUI 的 send/abort/approve/session.* 在 `tui/dispatch.dispatch`(JSON-RPC METHOD_*)。每加一个命令要在多个入口重复接线。

会话能力底层齐备但无命令入口(已核实):
- `session.manager.clear(session_id)`(L681,async,持锁)、`load`/`save`/`list_session_ids`
- `runtime.context.maybe_compress(messages, *, force, session_id, user_id, agent_name)`(L118)、`estimate_tokens(messages)`(L82)
- `observability.usage.get_usage_summary(UsageQuery(session_id=...)) -> UsageSummary`(L49;字段 run_count/prompt_tokens/completion_tokens/total_tokens/by_model,**无 USD cost 字段**)
- `runtime.budget.BudgetConfig/BudgetUsage`(per-run 预算:max_turns/max_tokens,非持久化 USD)

入口的会话归属:TUI 每连接有 `session_id`;IM 每 thread/DM 有 `session_id`;CLI 一次性 `run_sync` **无 session**(无状态)。

## Goals / Non-Goals

**Goals:**
- 一个共享命令分发器,命令逻辑写一次,TUI + IM 各接一次。
- 落地 `/clear` `/compact` `/context` `/usage` `/cost`,作用于当前会话。
- IM 侧命令位于访问门之后(仅授权用户)。
- 把 `/user` 迁入分发器统一(不改其外部行为)。

**Non-Goals:**
- 不在 CLI 一次性入口提供会话命令(无 session)。
- 不动 `/approve`(挂起/恢复语义特殊,本轮保持原状)。
- 不引入 USD 定价模型;`/cost` 以 token/预算口径呈现。
- 不在 IM 上 `/new`(thread 内"新会话"语义模糊)。
- 不做运行时 `/model` 切换(改动面大,另案)。

## Decisions

### D1:共享分发器 `runtime/commands.py`
```python
@dataclass
class CommandContext:
    agent_id: str | None
    session_id: str | None
    user_id: str | None

async def handle_command(ctx: CommandContext, text: str) -> str | None:
    """非 /命令 → None(交回正常对话);命中 → 回执文本(不进 loop)。"""
```
内部一个 `{name: handler}` 注册表;`handler(ctx, args) -> str`。`async` 因 clear/compact/load/save 是异步。`/user` 作为已注册命令并入(分发器调用 `user_instructions.handle_user_command`,后者保留)。

*备选:每命令各写 handle_xxx 四处接线 —— 否决,正是要消除的重复。*

### D2:作用域 = 有 session 的入口(TUI + IM)
会话命令需要 `session_id`。当 `ctx.session_id is None`(如 CLI 一次性)时,会话命令返回明确提示(「当前入口无会话,命令不可用」)而非误操作。`/user` 不依赖 session(agent 级),`ctx.session_id` 为 None 仍可用 —— 所以 CLI 仍能 `/user`。

### D3:IM 接线在访问门之后
`normalizer.route` 中,把现有 `/user` 拦截点替换为对 `handle_command` 的统一调用(位置不变:审批命令之后、access gate 通过之后、进 loop 之前)。命中即 `reply_func(回执)` 并 return,不跑 loop。容忍前导 @mention(复用 `_strip_leading_mention`)。

### D4:`/clear` 与 `/compact` 持锁改写
两者都 mutate 会话文件,必须在 `session_lock(session_id)` 内 load→处理→save:
- `/clear` → `manager.clear(session_id)`(其自身已持锁)。
- `/compact` → 持锁 `msgs=load`;`new=maybe_compress(msgs, force=True, session_id, user_id, agent_name)`;`save`;回执报告「N→M 条 / token 变化」。

### D5:`/context` `/usage` `/cost` 只读
- `/context` → `msgs=load(session_id)`;回执:消息数 + `estimate_tokens(msgs)` + 占 max_tokens 百分比。
- `/usage` → `get_usage_summary(UsageQuery(session_id=...))`;回执:run 数、prompt/completion/total tokens、按模型分。
- `/cost` → 无 USD 定价:回执呈现本会话 token 总量 + 该 agent 的 budget 上限(max_turns/max_tokens)与消耗占比;文案明确「token/预算口径,非美元」。若 budget 未配置,仅报 token 总量。

### D6:回执文案带「这是会话级操作」语义
`/clear` `/compact` 改变共享会话状态,回执明确告知影响范围(当前 thread/DM 会话),与 `/user`(agent 级)区分。

## Risks / Trade-offs

- **[IM `/clear` 误清]** thread 内 `/clear` 清空该会话历史不可逆 → 回执明确「已清空当前会话」;不做 `/new`,降低歧义。未来可加二次确认(本轮不做)。
- **[`/cost` 期望落差]** 用户可能期待美元金额 → 文案显式声明 token/预算口径;真实定价是后续独立能力。
- **[并发]** 同会话并发 `/clear`+正常消息 → clear/compact 走 `session_lock`,与 loop 的会话锁同源,序列化安全。
- **[CLI 误用]** 用户在 CLI 一次性敲 `/clear` → `session_id is None` 返回提示,不静默吞掉。

## Migration Plan

纯新增 + 一处重构(`/user` 接线改走分发器,行为不变)。回滚 = 移除分发器接线、恢复 `/user` 直连。无数据迁移。

## Open Questions

无 —— 范围(5 命令)、架构(共享分发器)、IM 覆盖(访问门后)已与用户敲定;`/cost` 的 token 口径已明确为本轮约束。
