# multimodal-input Specification

## Purpose
TBD - created by archiving change multimodal-input. Update Purpose after archive.
## Requirements
### Requirement: 接受图片内容并透传 LLM

主循环（`run()` / `run_stream()`）SHALL 接受消息 `content` 为文本与图片混合的内容块数组，并将其原样透传给 LLM 调用。当 `content` 为内容块数组时，主循环 MUST NOT 假设其为字符串。

#### Scenario: 含图片的消息透传给 LLM
- **WHEN** 主循环收到一条 `content` 为「文本块 + 图片块」数组的 user 消息
- **THEN** 该内容块数组被原样传给 LLM 调用，不被丢弃或转为纯文本

#### Scenario: 纯文本消息行为不变
- **WHEN** 主循环收到 `content` 为字符串的消息
- **THEN** 行为与现状完全一致，走纯文本路径

### Requirement: base64 编码图片作为消息内容

平台 SHALL 支持以 base64 data URL 内联承载图片，作为 `image_url` 内容块的 `url`。图片数据 MUST 随消息体内联，MUST NOT 依赖外部图床或对象存储（数据不出内网）。

#### Scenario: 图片以 base64 data URL 内联
- **WHEN** 构造一条含图片的消息
- **THEN** 图片以 `data:{mime};base64,{...}` 形式作为 `image_url` 内容块承载，不引用外部 URL

### Requirement: 含图片时路由到视觉模型

当消息序列含图片内容块时，主循环 SHALL 路由到 model_router 的 `vision` task_type（视觉能力模型），而非默认 chat 模型。当含图片但未配置 `vision` 路由时，主循环 MUST 抛出明确错误，MUST NOT 将图片静默发给非视觉模型。

#### Scenario: 含图片路由到视觉模型
- **WHEN** 主循环处理一条含图片块的消息且已配置 vision 路由
- **THEN** 该轮 LLM 调用使用 vision task_type 对应的视觉模型

#### Scenario: 纯文本不触发视觉路由
- **WHEN** 消息不含图片块
- **THEN** 主循环使用默认 chat 路由，行为与现状一致

#### Scenario: 未配置视觉路由时报错
- **WHEN** 消息含图片块但未配置 vision task_type 路由
- **THEN** 主循环抛出明确错误，且不发起对非视觉模型的调用

### Requirement: 图片内容不破坏压缩与 trace

含图片内容块的消息进入上下文压缩与运行日志时，图片块 SHALL 按占位处理：token 估算 MUST NOT 将 base64 巨串计入字符数，trace MUST NOT 写入完整 base64 串。

#### Scenario: 大图不撑爆 token 估算
- **WHEN** 一条消息含大体积 base64 图片块进入 token 估算
- **THEN** 估算按固定占位计量图片块，不因 base64 长度误判为超阈值

#### Scenario: trace 中图片以占位记录
- **WHEN** 含图片块的运行写入 trace
- **THEN** trace 中图片块被替换为占位（含 mime 与大小），不含完整 base64 串

### Requirement: 音频视频不支持，非图片二进制降级占位

平台 MUST NOT 透传音频或视频内容给 LLM。输入若含非图片、非文本的二进制内容，平台 SHALL 将其归一化为文本占位提示，而非塞入 image_url。

#### Scenario: 音视频内容不透传
- **WHEN** 输入包含音频或视频内容
- **THEN** 该内容不被作为 image_url 透传，按不支持处理

#### Scenario: 非图片二进制降级为占位
- **WHEN** 输入包含非图片、非文本的二进制附件
- **THEN** 该附件被归一化为文本占位提示，已有的文本内容仍正常传给 LLM

