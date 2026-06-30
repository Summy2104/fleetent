## ADDED Requirements

### Requirement: Telegram 适配器上传生成图片到原会话

Telegram 适配器构造的入站 `NormalizedMessage` SHALL 设置 `upload_func`，使本轮 agent 产出的生成图片/文件自动投回原会话，镜像 Slack 行为。该 `upload_func` SHALL 收敛到统一出站文件原语（`outbound.send_file_to`），按本会话地址（`ConversationAddress`：私聊/群组/话题）投递。单个文件投递失败时 MUST 记 warning 并继续处理其余文件，MUST NOT 中断响应。Telegram 适配器入站 MUST NOT 再缺失 `upload_func`（此前为 None，导致生成图片不自动投递）。

#### Scenario: Telegram 生成图片自动投回原会话

- **WHEN** 一轮 Telegram 触发的 run 产出生成图片
- **THEN** 适配器经 `upload_func` → 统一出站文件原语把图片投回原会话（私聊/群组/话题）

#### Scenario: 单个上传失败优雅降级

- **WHEN** 某个生成文件投递失败
- **THEN** 记 warning，跳过该文件，继续处理其余路径，文字响应已正常发出

#### Scenario: Telegram 入站 upload_func 非空

- **WHEN** Telegram 适配器构造入站 `NormalizedMessage`
- **THEN** 其 `upload_func` 非空（不再是 None）
