## ADDED Requirements

### Requirement: provider registry 以 protocol 为键分发图像生成请求

平台 SHALL 维护一个以 `agent.yaml` `ModelTarget.protocol` 字段为键的 provider registry。每次图像生成调用 MUST 通过 registry 查找对应 provider，找不到时 MUST 抛出 `ImageGenError` 并说明未知协议名称。

#### Scenario: 已注册 provider 正常分发
- **WHEN** `image_generation` route 的 `protocol` 与注册表中某 provider 匹配
- **THEN** 请求分发至该 provider，返回图像字节

#### Scenario: 未知协议时明确失败
- **WHEN** `image_generation` route 的 `protocol` 在 registry 中无对应 provider
- **THEN** 抛出 `ImageGenError`，错误信息包含未知协议名称，不崩溃主循环

### Requirement: 内置 OpenAIImagesProvider 处理 openai_image_generation 协议

平台 SHALL 内置 `OpenAIImagesProvider`，处理 `protocol: openai_image_generation`，调用 `endpoint` 所指 OpenAI 兼容 `/v1/images/generations`，行为 MUST 与现有实现完全一致（`response_format=b64_json`，URL fallback）。

#### Scenario: b64_json 响应正常解码
- **WHEN** `openai_image_generation` provider 调用端点，响应含 `data[0].b64_json`
- **THEN** base64 解码为图像字节返回

#### Scenario: url 响应时下载字节
- **WHEN** 响应含 `data[0].url` 而非 `b64_json`
- **THEN** 从该 URL 下载图像字节返回

#### Scenario: 端点调用失败时抛 ImageGenError
- **WHEN** endpoint 调用返回错误或超时
- **THEN** 抛出 `ImageGenError`，不崩溃主循环

### Requirement: 内置 ChatImageProvider 处理 openai_image_chat 协议

平台 SHALL 内置 `ChatImageProvider`，处理 `protocol: openai_image_chat`，通过 `base_url` 调用 Chat Completions API，从响应 content 提取 `data:image/<ext>;base64,<data>` 或裸 HTTP URL 形式的图像。

#### Scenario: content 含 data URI 时提取 base64
- **WHEN** `openai_image_chat` provider 收到 Chat Completions 响应，content 含 `data:image/...;base64,...`
- **THEN** 解码 base64 为图像字节返回

#### Scenario: content 含裸 URL 时下载图像
- **WHEN** response content 以 `http` 开头（裸 URL）
- **THEN** 从该 URL 下载图像字节返回

#### Scenario: content 既无 data URI 也无 URL 时抛 ImageGenError
- **WHEN** response content 不含可识别的图像数据
- **THEN** 抛出 `ImageGenError`，错误信息包含 content 前 200 字符，便于诊断

#### Scenario: 空响应时抛 ImageGenError
- **WHEN** Chat Completions 响应 choices 为空或 content 为空字符串
- **THEN** 抛出 `ImageGenError`

### Requirement: agent.yaml 支持 openai_image_chat 协议配置

`agent.yaml` 的 `ModelTarget` MUST 支持 `protocol: openai_image_chat`，该协议 MUST 要求 `base_url` 和 `model` 字段，缺失时 MUST 在配置加载阶段报 `ValueError`。

#### Scenario: base_url + model 均填写时配置合法
- **WHEN** `agent.yaml` 中 target 指定 `protocol: openai_image_chat`，同时提供 `base_url` 和 `model`
- **THEN** 配置加载成功，无报错

#### Scenario: 缺少 base_url 时拒绝加载
- **WHEN** `protocol: openai_image_chat` 的 target 缺少 `base_url`
- **THEN** 配置加载抛 `ValueError`

#### Scenario: 缺少 model 时拒绝加载
- **WHEN** `protocol: openai_image_chat` 的 target 缺少 `model`
- **THEN** 配置加载抛 `ValueError`

### Requirement: image_gen_client 向后兼容

`fleetent.tools.image_gen_client` 模块 MUST 继续导出 `generate` 函数和 `ImageGenError` 类，其类型标识 MUST 与 `fleetent.tools.image_gen` 包导出的对象相同（`is` 检查通过），现有 import 无需修改。

#### Scenario: shim 导出与 image_gen 包同一对象
- **WHEN** 从 `image_gen_client` 和 `image_gen` 分别 import `generate` 和 `ImageGenError`
- **THEN** 两者为同一对象（`is` 返回 True）
