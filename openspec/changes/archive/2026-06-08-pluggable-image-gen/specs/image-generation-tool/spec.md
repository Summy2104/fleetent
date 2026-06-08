## MODIFIED Requirements

### Requirement: 后端为自托管 OpenAI 兼容 images 端点

图片生成 SHALL 调用由配置指定的 OpenAI 兼容后端。平台 MUST 支持两种协议：

1. `openai_image_generation`：调用 `/v1/images/generations` 端点（`endpoint` 字段），要求端点可自托管、数据不出内网
2. `openai_image_chat`：通过 Chat Completions API（`base_url` 字段）调用，从响应 content 提取图像，适用于 Gemini 等通过 Chat API 生成图像的模型

平台 MUST NOT 调用云托管专有图像服务（如 DALL·E 云端 / Midjourney）。

#### Scenario: openai_image_generation 协议经配置端点生成
- **WHEN** `generate_image` 执行且 route target 使用 `protocol: openai_image_generation` 并已配置 `endpoint`
- **THEN** 经该 OpenAI 兼容 images 端点生成图片，图片数据不出内网

#### Scenario: openai_image_chat 协议经 Chat Completions 生成
- **WHEN** `generate_image` 执行且 route target 使用 `protocol: openai_image_chat` 并已配置 `base_url`
- **THEN** 经 Chat Completions API 调用，从响应中提取图像字节

#### Scenario: 未配置端点时明确失败
- **WHEN** `generate_image` 执行但 `image_generation` route 未配置或协议无对应 provider
- **THEN** 工具以明确错误结果返回（不静默成功），不崩溃主循环
