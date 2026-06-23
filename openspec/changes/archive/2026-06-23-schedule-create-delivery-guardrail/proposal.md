## Why

通过对话创建定时任务时,模型反复踩同一个坑:把投递目标**写进 `message`**(「把结果私信发送给 X」)而**不配 `deliver`/`notify_target`**。后果:`deliver=None` 回退广播到创建会话的频道(投错地方/刷屏),且模型在 run 内又自发(双投递)。这是个会反复中招的 footgun——`schedule` 工具其实提供了正确旋钮(`notify_target` 配投递、`task_type=action` 让 agent 自发),但模型不用。

## What Changes

- `schedule_store.create` 新增 **创建期护栏**:当 `task_type="generate"` **且** 未配显式 `deliver` **且** `message` 命中发送祈使(私信/发送给/发给/推送给/发到/send to/DM)时,**拒绝**(抛 `ValueError`,经 `schedule` 工具转为干净的 `error:` 文案),提示改用 `notify_target` 配投递目标、或 `task_type=action` 让 agent 自己发送。
- `schedule` 工具描述/参数说明补一句原则:**投递目标用 `notify_target` 配置、不要写进 `message`;`generate` 的回复由调度器投递(不自发),`action` 才由 agent 自己发送**(随 schema 下发给模型)。
- 仅创建期校验 + 文案引导;不改调度/投递语义。范围保守:护栏只在「generate + 无 deliver + message 含发送祈使」三条同时成立时触发,误报代价低(仅促使把投递显式化)。

## Capabilities

### Modified Capabilities
- `cron-scheduled-tasks`:`schedule_store` 的 per-type 校验新增「generate + 无 deliver + message 含发送祈使 → 拒绝并引导」;`schedule` 工具参数说明补充投递配置原则。

## Impact

- **owning package**:`schedule_store`(create 校验)、`tools/`(`schedule` 工具 docstring/参数说明)。
- **public API surface**:`schedule_store.create` 在 footgun 组合下新增 `ValueError`(既有 caller 已捕获 ValueError → `error:` 文案);其余不变。
- **owned tables / config / migration**:无。
- **cross-module dependencies**:无新增;零 `fleetent.platform.*` import。
