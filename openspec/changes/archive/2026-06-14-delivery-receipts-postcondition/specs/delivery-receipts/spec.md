# delivery-receipts Delta

## ADDED Requirements

### Requirement: outbound 原语返回结构化投递回执

`outbound.send_to` 与 `outbound.send_file_to` SHALL 返回结构化回执 `{ok, platform, target, target_type, kind(text|file), thread, provider_ref, error}`：成功时 `ok=true` 且尽可能携带平台凭证（Slack 消息 ts / 文件 id）；失败时 `ok=false` 携带原因。原语 MUST 保持永不抛的既有语义（失败=失败回执，非异常）。

#### Scenario: 文本投递成功回执

- **WHEN** `send_to` 向 Slack 频道成功投递文本
- **THEN** 返回回执 `ok=true, kind="text"`，含目标与平台 ts

#### Scenario: 文件投递失败回执

- **WHEN** `send_file_to` 因网络错误投递失败
- **THEN** 返回回执 `ok=false, kind="file"` 且 `error` 描述原因，不抛异常

### Requirement: run 级投递台账与 delivery trace 事件

一次 run 内经 outbound 原语的全部投递尝试（send_file、send_im_message、生成图上传、cron fire 投递）SHALL 记入该 run 的投递台账，并各写一条 `event_type="delivery"` trace 事件（payload 为回执字段，目标经脱敏基线）。trace 写入失败 MUST 仅记 warning，MUST NOT 影响投递结果与 run。

#### Scenario: 工具投递进台账与 traces

- **WHEN** 一次 run 中 send_file 成功发送一个文件
- **THEN** run 台账含该回执，traces 出现一条 `delivery` 事件（ok=true, kind=file）

#### Scenario: cron fire 投递留痕

- **WHEN** 定时任务 fire 并向 origin 投递回复
- **THEN** traces 出现对应 `delivery` 事件，任务行 last_status/last_error 语义不变

### Requirement: 最终回复附加事实投递尾注

当一次 run 的投递台账非空时，系统 SHALL 在最终回复之后追加一行由台账确定性渲染的投递尾注，列明成功/失败的投递（kind、数量、目标摘要、失败原因摘要）；台账为空（本轮无任何出站尝试）时 MUST NOT 追加。尾注 MUST 由系统在模型回复文本之外拼接，模型输出 MUST NOT 能替代或移除它。流式回复路径 SHALL 在流结束后以独立消息补发尾注。

#### Scenario: 有投递则尾注列明事实

- **WHEN** 一次 run 成功发送 1 个文件并有 1 次失败的消息投递
- **THEN** 最终回复后出现尾注，含"文件 1（成功）"与"消息 1（失败：原因）"

#### Scenario: 无出站尝试无尾注

- **WHEN** 一次纯问答 run 未触发任何 outbound 原语
- **THEN** 回复后不出现尾注

#### Scenario: 虚报被尾注暴露

- **WHEN** 模型回复声称"文件已通过 Slack 发送"但本轮 send_file/上传从未执行
- **THEN** 尾注如实显示文件投递为 0（或不含文件项），用户可见声明与事实不符

#### Scenario: MCP 外发不被背书

- **WHEN** 模型经 MCP 工具（如第三方邮件 server）声称完成外发，本轮 fleetent 原语无对应投递
- **THEN** 尾注不包含该"投递"，仅列 fleetent 可证实的条目
