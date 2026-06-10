## ADDED Requirements

### Requirement: NormalizedMessage 携带会话上下文元数据

`NormalizedMessage` SHALL 携带可选字段 `session_context`(默认 `None`),由 IM 适配器填充,
载有发起人与渠道元数据:`platform`、`sender_id`、`sender_name`、`chat_type`(`dm`/`channel`)、
`channel_name`、`was_mentioned`、`thread_root`。为 `None` 时,注入行为整体跳过,与未引入时一致。

#### Scenario: 适配器填充 session_context

- **WHEN** Slack 适配器规范化一条 DM 消息(用户 `U123`)
- **THEN** `NormalizedMessage.session_context` 含 `platform="slack"`、`sender_id="U123"`、`chat_type="dm"`
- **AND** 频道消息额外含 `channel_name` 与 `was_mentioned`

#### Scenario: 不填 session_context 时行为不变

- **WHEN** 适配器构造 `NormalizedMessage` 未设 `session_context`
- **THEN** 不注入任何发起人/渠道/时间上下文,LLM 输入与未引入本能力时一致

### Requirement: 发起人/渠道/时间注入 LLM 上下文

当 `session_context` 存在时,系统 SHALL 将「会话框架」注入 **system 消息段**(platform、
DM 或频道、频道名、当前日期+时区),并将「本条发送人」注入 **user 消息前缀**
(`sender_id` + `sender_name` + 是否 @bot)。时间为日期级以保 prompt cache。

#### Scenario: 会话框架注入 system 段

- **WHEN** 一条 Slack 频道消息带 `session_context`
- **THEN** system 消息含 platform、频道标识(频道名)、当前日期与时区
- **AND** DM 场景标注为私信

#### Scenario: 发送人注入 user 前缀

- **WHEN** 处理一条带 `session_context` 的消息
- **THEN** 本次 user 消息前含一段紧凑发送人信息(`sender_id`、`sender_name`、是否@bot)
- **AND** LLM 可据此回报发起人 Slack ID

#### Scenario: 时间为日期级

- **WHEN** 注入当前时间
- **THEN** 注入到日期粒度(不含分钟),附时区,避免每条消息扰动可缓存前缀

### Requirement: whoami 工具按需返回发起人身份

系统 SHALL 提供内置工具 `whoami`,返回当前会话的发起人 `sender_id`、`sender_name`、
`platform`、`chat_type`、`channel_name` 与当前时间。上下文不可用时返回「未知」而非报错。

#### Scenario: whoami 返回发起人身份

- **WHEN** agent 在一条带 `session_context` 的 Slack 消息处理中调用 `whoami`
- **THEN** 返回含该发起人的 `sender_id`(如 `U123`)、`sender_name`、`platform`、`chat_type`

#### Scenario: 上下文缺失时降级

- **WHEN** 调用 `whoami` 但当前无 `session_context`(如 CLI 直跑)
- **THEN** 返回标注「未知/不可用」,不抛异常,不中断 run
