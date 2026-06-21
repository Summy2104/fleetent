## Why

fleetent 各入口的命令面不齐:TUI 有 `/new` `/session` `/abort` `/approve` `/help` `/user`,IM 只有审批 + `/user`,而「清空会话、压缩上下文、查看 token 占用/用量」这些能力**底层都已实现,却没有任何用户命令入口**(只能走 admin API/CLI)。终端用户无法在对话中自助管理会话。同时命令逻辑分散(审批在 normalizer、`/user` 在 user_instructions、TUI 方法在 dispatch),每加一个命令都要在四处重复接线。

## What Changes

- 新增 **共享命令分发器** `runtime/commands.py`:统一命令注册表 + `handle_command(ctx, text) -> str | None`(沿用 `/user` 的「`None`=非命令、非空=回执且不进 loop」契约),`ctx` 携带 `agent_id` / `session_id` / `user_id`。
- 新增 **5 个会话命令**(均会话型,作用于当前 `session_id`):
  - `/clear` —— 清空当前会话历史(复用 `session.manager.clear`)
  - `/compact` —— 手动压缩上下文(复用 `context.maybe_compress(force=True)`)
  - `/context` —— 查看当前消息数 + token 估算占用(复用 `context.estimate_tokens`)
  - `/usage` —— 本会话 token 用量(复用 `observability.usage.get_usage_summary`)
  - `/cost` —— 预算消耗/上限(基于 budget 配置 + 本会话 token 总量;**fleetent 无 USD 定价模型,以 token/预算口径呈现,非美元**)
- 命令在 **TUI + IM(Slack/Telegram)** 两个有会话的入口可用;IM 侧位于**访问门之后**(仅授权用户)。CLI 一次性 `fleetent "prompt"` 无状态、无 session,这些会话命令在该入口不适用(仅 `/user` 这种 agent 级命令保留)。
- 将现有 `/user` 迁入共享分发器统一(`user_instructions` 的函数保留,分发器内部调用),`/approve` 因涉及挂起/恢复较特殊,本轮不动。

## Capabilities

### New Capabilities
- `session-commands`: 共享命令分发器的契约(`handle_command` 语义、`ctx` 字段、跨入口一致性、IM 访问门约束),以及 `/clear` `/compact` `/context` `/usage` `/cost` 五个命令各自的行为与边界。

### Modified Capabilities
<!-- 无:复用既有 session/context/usage/budget 能力,不改其要求;`/user` 迁入是实现重构,不改 user-instructions 的 spec 行为。 -->

## Impact

- **owning package**:`runtime`(新增 `runtime/commands.py`)。
- **public API surface**:`handle_command(ctx, text) -> str | None`、命令注册结构、`CommandContext` dataclass。
- **owned tables**:无(读现有 session 文件 / usage trace,不新增表)。
- **config namespace**:无。
- **cross-module dependencies**:`session.manager`(clear/load/save)、`runtime.context`(maybe_compress/estimate_tokens)、`observability.usage`(get_usage_summary)、`runtime.budget`(预算口径);接线触碰 `im_gateway.normalizer`、`tui`(dispatch/app/backend/protocol)。
- **migration / shim plan**:`/user` 迁入分发器时保留 `user_instructions.handle_user_command` 不删,避免破坏现有接线;新分发器在其之上聚合。
- **解耦约束**:纯 agent 侧,严禁触碰 platform 表,符合 Agent/Platform 单向依赖。
