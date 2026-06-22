# session-commands Specification

## Purpose
TBD - created by archiving change session-commands. Update Purpose after archive.
## Requirements
### Requirement: 共享命令分发器
系统 SHALL 提供一个共享命令分发器 `runtime/commands.py`,暴露 `handle_command(ctx, text) -> str | None`,其中 `ctx` 携带 `agent_id` / `session_id` / `user_id`。对非命令文本返回 `None`(交回正常对话);命中命令时执行并返回给用户的回执文本,且该输入 MUST NOT 进入 agent loop。命令逻辑集中于此,各入口仅调用一次。

#### Scenario: 非命令返回 None
- **WHEN** 调用 `handle_command(ctx, "你好")`
- **THEN** 返回 `None`

#### Scenario: 命中命令返回回执且不跑 loop
- **WHEN** 调用 `handle_command(ctx, "/context")` 且 ctx.session_id 有效
- **THEN** 返回非 `None` 回执,调用方据此回复用户而不触发一次对话

### Requirement: 会话命令需要会话上下文
当命令为会话型(`/clear` `/compact` `/context` `/usage` `/cost`)而 `ctx.session_id` 为 `None` 时,系统 SHALL 返回明确提示(当前入口无会话、命令不可用),MUST NOT 误操作或抛异常。agent 级命令(`/user`)不受此限,`session_id` 为 None 仍可用。

#### Scenario: 无会话入口拒绝会话命令
- **WHEN** `ctx.session_id is None`,调用 `handle_command(ctx, "/clear")`
- **THEN** 返回「当前入口无会话,命令不可用」类提示,不修改任何会话

#### Scenario: 无会话仍可用 agent 级命令
- **WHEN** `ctx.session_id is None`,调用 `handle_command(ctx, "/user")`
- **THEN** 正常返回 user.md 内容(或未设置提示)

### Requirement: /clear 清空当前会话
系统 SHALL 支持 `/clear`,在 `session_lock` 下清空 `ctx.session_id` 的会话历史(复用 `session.manager.clear`),返回已清空回执,回执明确指出影响范围为当前会话。

#### Scenario: 清空非空会话
- **WHEN** 当前会话有历史,调用 `/clear`
- **THEN** 该会话历史被清空,返回已清空回执

#### Scenario: 清空空会话幂等
- **WHEN** 当前会话已为空,调用 `/clear`
- **THEN** 不抛异常,返回已清空回执

### Requirement: /compact 手动压缩上下文
系统 SHALL 支持 `/compact`,在 `session_lock` 下加载当前会话、以 `maybe_compress(..., force=True)` 压缩、保存结果,返回压缩前后消息数/token 变化的回执。

#### Scenario: 压缩长会话
- **WHEN** 当前会话消息较多,调用 `/compact`
- **THEN** 会话被压缩并保存,回执报告压缩前后的消息数或 token 变化

### Requirement: /context 查看上下文占用
系统 SHALL 支持 `/context`,加载当前会话并以 `estimate_tokens` 估算,返回消息数、估算 token 数及相对上限的占用情况。只读,不改会话。

#### Scenario: 查看上下文
- **WHEN** 调用 `/context`
- **THEN** 返回当前会话消息数与 token 估算占用,且会话内容不变

### Requirement: /usage 查看本会话用量
系统 SHALL 支持 `/usage`,以 `get_usage_summary(UsageQuery(session_id=...))` 查询并返回本会话的 run 数与 prompt/completion/total token 用量。只读。

#### Scenario: 查看用量
- **WHEN** 调用 `/usage`
- **THEN** 返回本会话的 run 数与 token 用量汇总

### Requirement: /cost 查看预算口径消耗
系统 SHALL 支持 `/cost`,以 token/预算口径(非 USD)呈现本会话 token 总量与该 agent 的预算上限/消耗占比。回执 MUST 明确说明为 token/预算口径而非美元金额。budget 未配置时仅呈现 token 总量。

#### Scenario: 查看成本(token 口径)
- **WHEN** 调用 `/cost`
- **THEN** 返回本会话 token 总量(及预算占比),且回执标明为 token/预算口径、非美元

### Requirement: 命令在 TUI 与 IM 跨入口可用且一致
系统 SHALL 在 TUI 与 IM(Slack/Telegram)两个有会话的入口提供上述命令,语义一致,均经同一 `handle_command` 实现。IM 侧的命令处理 MUST 位于访问门之后(仅授权用户可执行),并容忍前导 @mention。

#### Scenario: IM 授权用户执行命令
- **WHEN** 授权用户经 Slack 发送 `/clear`
- **THEN** normalizer 在访问门通过后、进 loop 前调用 `handle_command`,清空会话并回复回执,不触发一次对话

#### Scenario: IM 未授权用户被门挡住
- **WHEN** 未授权用户经 IM 发送 `/clear`
- **THEN** 访问门拒绝,命令不被执行

#### Scenario: TUI 执行命令
- **WHEN** 用户在 TUI 输入 `/context`
- **THEN** 经服务端 `handle_command` 返回上下文占用回执

### Requirement: /user 迁入共享分发器
系统 SHALL 将既有 `/user` 命令并入共享分发器统一处理(分发器内部调用 `user_instructions.handle_user_command`,后者保留),`/user` 的查看/追加/清空外部行为不变。

#### Scenario: /user 经分发器仍可用
- **WHEN** 调用 `handle_command(ctx, "/user 永远用中文回答")`
- **THEN** 追加到该 agent 的 user.md 并返回回执,行为与迁入前一致

