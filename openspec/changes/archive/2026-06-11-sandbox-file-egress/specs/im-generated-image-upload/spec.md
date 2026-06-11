## MODIFIED Requirements

### Requirement: normalizer 从本轮工具结果提取生成图片路径

正则嗅探自动回流 SHALL 废弃：`route()` MUST NOT 再依赖扫描本轮 tool 结果里的 `"image generated: <path>"` / `"written N bytes to <path>"` 文本、并用宿主 `Path.is_file()` 判存在后自动上传。在沙箱优先执行下，`run_code` / `write_file` 在**容器内**写文件、工具结果回的是**容器内路径**，宿主 `Path.is_file()` 结构性命不中（容器路径在宿主不存在），该机制对容器世界失效。

过渡期内系统 MUST 杜绝"静默漏发"：当本轮确有生成型工具产物却因上述结构性失效无法宿主命中时，`route()` MUST 给用户一条显式"外发失败：请用 `send_file` 工具发送产物"的提示，而非静默跳过。沙箱产物送回用户的正路是 `sandbox-file-send` 的 `send_file` 工具（agent 显式调用），而非宿主端正则推断。

#### Scenario: 容器内产物不再被宿主正则命中而静默丢弃

- **WHEN** 本轮 `run_code` / `write_file` 在容器内生成文件，工具结果含容器内路径（如 `/workspace/out.png`）
- **THEN** `route()` MUST NOT 用宿主 `Path.is_file()` 判存在后自动上传该路径（宿主必然命不中）

#### Scenario: 本轮有产物却无法宿主命中时显式提示而非静默漏发

- **WHEN** 本轮确有生成型工具产物，但因容器/宿主路径分歧无法在宿主命中
- **THEN** `route()` 给用户显式"外发失败：请用 send_file 发送"提示，MUST NOT 静默跳过

#### Scenario: 显式 send_file 是产物送回正路

- **WHEN** agent 需要把本轮 workspace 产物送回当前发起人
- **THEN** 经 `send_file` 工具显式发送，而非依赖 normalizer 端正则嗅探推断

### Requirement: Slack 适配器上传生成图片到原线程

出站文件投递 SHALL 收敛到统一出站文件原语（`outbound` 顶层基础设施），由其按平台分派；Slack 路径复用 `client.files_upload_v2(channel=channel, thread_ts=reply_thread, file=path)`，行为与收敛前一致。单个文件投递失败时 MUST 记 warning 并继续处理其余文件，MUST NOT 中断响应。该出站文件原语同时被 `sandbox-file-send` 的 `send_file` 工具复用，使工具外发与适配器上传走同一投递实现。

#### Scenario: Slack 出站文件经统一原语投递

- **WHEN** 需要把一个本地文件作为附件发到 Slack 线程
- **THEN** 经统一出站文件原语调用 `files_upload_v2(channel, thread_ts, file)` 投递到原线程，行为与收敛前一致

#### Scenario: 单个上传失败优雅降级

- **WHEN** `files_upload_v2` 对某个路径抛异常
- **THEN** 记 warning，跳过该文件，继续处理其余路径，文字响应已正常发出

#### Scenario: send_file 工具与适配器共享同一投递实现

- **WHEN** `send_file` 工具在 Slack 会话发送 workspace 产物
- **THEN** 它经同一统一出站文件原语投递，而非各自实现一套 Slack 上传

## ADDED Requirements

### Requirement: Telegram 适配器支持出站文件投递

统一出站文件原语 SHALL 新增 Telegram 出站文件路径：经 `bot.send_document(chat_id=..., document=...)` 把本地文件作为文档投递（此前 Telegram 出站只有 `send_message` 文本，无任何出站文件能力）。投递失败时 MUST 记 warning 并返回失败信号，MUST NOT 抛异常中断调用方。Telegram 与 Slack 共用统一出站文件原语的平台分派范式（对齐 `outbound.send_to` 既有按 `platform` 分派的结构）。

#### Scenario: Telegram 出站文件经 send_document 投递

- **WHEN** 需要把一个本地文件作为附件发到 Telegram 某 chat
- **THEN** 统一出站文件原语经 `bot.send_document(chat_id, document)` 投递该文件

#### Scenario: Telegram 出站投递失败不抛

- **WHEN** `send_document` 抛错（网络/权限/不可达）
- **THEN** 原语记 warning 并返回失败信号，MUST NOT 向调用方抛异常

#### Scenario: send_file 在 Telegram 会话复用该路径

- **WHEN** `send_file` 工具在 Telegram DM 会话发送 workspace 产物
- **THEN** 它经统一出站文件原语的 Telegram `send_document` 路径投递
