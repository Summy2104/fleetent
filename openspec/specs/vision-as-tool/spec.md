# vision-as-tool Specification

## Purpose
TBD - created by archiving change vision-as-tool. Update Purpose after archive.
## Requirements
### Requirement: 图像理解经 analyze_image 工具按需提供

系统 SHALL 提供 `analyze_image(ref, instruction)` 工具,对一张已存盘的入站图片调用自托管 VLM 端点,返回该图片的结构化文本理解结果。工具结果 MUST NOT 包含图片的 base64 数据(仅返回文本理解)。当 `ref` 无效(盘上无此图)或 VLM 端点未配置/调用失败时,工具 MUST 返回明确的错误结果文本,且 MUST NOT 抛出异常中断 agent 循环。VLM 端点 MUST 为自托管 OpenAI 兼容服务,MUST NOT 引入云托管专有视觉服务。

#### Scenario: 按引用理解图片返回文本
- **WHEN** agent 对一个有效的图片引用与一句 instruction 调用 `analyze_image`
- **THEN** 工具对自托管 VLM 做一次聚焦调用,返回针对该 instruction 的结构化文本结果,结果中不含 base64

#### Scenario: 无效引用返回错误文本
- **WHEN** `analyze_image` 收到一个盘上不存在的图片引用
- **THEN** 返回说明引用无效的错误结果文本,不抛出异常、不中断循环

#### Scenario: 端点未配置返回错误文本
- **WHEN** VLM 端点未配置(`vision_url` 为空)而 `analyze_image` 被调用
- **THEN** 返回说明端点未配置的明确失败文本,不静默成功、不中断循环

### Requirement: 入站图片存盘,主上下文仅带引用

入站图片 SHALL 写入可注入的 uploads 目录,主对话上下文 MUST 仅携带该图片的盘上引用而非 base64。`analyze_image` MUST 通过引用从盘上读取图片,而非要求 base64 在上下文中流转。

#### Scenario: 图片存盘并以引用入上下文
- **WHEN** 一条含图片的入站消息被处理
- **THEN** 图片字节被写入 uploads 目录,主上下文携带其引用(路径),不携带 base64

### Requirement: 含图消息首次自动抽取并回落文本路由

当一条入站消息含图片时,消息归一化链 SHALL 自动先调用一次 `analyze_image`(以用户文本作 instruction),将其文本结果注入对话,并将该图片块从主上下文剥离、替换为盘上引用。剥离后,后续轮次的路由 MUST 不再因该图片而走视觉路由(回落到文本路由);若模型需要再次查看图片,MUST 由模型主动再次调用 `analyze_image`。

#### Scenario: 首次自动抽取
- **WHEN** 一条含图片的消息进入归一化链
- **THEN** 链先自动调用一次 `analyze_image` 并把其文本结果注入对话,无需模型先主动请求

#### Scenario: 抽取后回落文本路由
- **WHEN** 首次抽取完成、图片块已被剥离为盘上引用
- **THEN** 后续轮次上下文不再含图片块,路由回落到文本(default)路由,不再按视觉模型计费

#### Scenario: 模型驱动的回看
- **WHEN** 抽取后的某轮模型判断需要再次查看该图片的其他细节
- **THEN** 模型主动调用 `analyze_image` 传入该引用与新 instruction,获得新的文本理解

