# image-generation-tool Specification

## Purpose
TBD - created by archiving change image-generation-tool. Update Purpose after archive.
## Requirements
### Requirement: 提供文生图工具 generate_image

平台 SHALL 提供一个 `generate_image` 工具，注册到工具注册表，供 AI 在对话中调用以从文本 prompt 生成图片。该工具 MUST 以 `low` 风险级别注册，因而 MUST NOT 触发人工审批门。

#### Scenario: AI 调用 generate_image 生成图片
- **WHEN** AI 在工具调用中请求 `generate_image` 并提供 prompt
- **THEN** 工具被 dispatch 执行，生成一张图片并返回结果，循环继续

#### Scenario: low 风险不触发审批
- **WHEN** `generate_image` 被调用
- **THEN** 不经过人工审批门，直接执行（与其它 low 风险工具一致）

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

### Requirement: 生成图存盘并返回短引用

生成的图片 SHALL 保存到 per-scope sandbox workspace 下的 `generated/` 目录(容器内 `/workspace/generated/`,= 宿主对应 workspace 子目录),工具返回值 MUST 为指向该图片的 **workspace 相对引用**(如 `generated/<name>.png`),MUST NOT 返回宿主绝对路径,MUST NOT 将图片 base64 内联进工具结果。该相对引用 MUST 满足 `sandbox-workspace-root` 的相对路径不变式:容器模式与无-docker 降级模式按同一相对引用解析到同一物理文件。生成图的 base64 数据 MUST NOT 进入对话上下文或运行日志(trace)。

#### Scenario: 返回 workspace 相对引用而非 base64
- **WHEN** `generate_image` 成功生成一张图片
- **THEN** 工具结果为指向已存盘图片的 workspace 相对引用(`generated/<name>.png`),不含 base64、不含宿主绝对路径

#### Scenario: 生成图落在 workspace/generated
- **WHEN** `generate_image` 成功生成一张图片
- **THEN** 图片字节被写入 per-scope workspace 的 `generated/` 子目录(容器内 `/workspace/generated/`),可经文件工具按 `generated/<name>.png` 读回

#### Scenario: trace 不含生成图 base64
- **WHEN** 一次含 `generate_image` 调用的运行写入 trace
- **THEN** trace 中不含生成图的完整 base64 串

### Requirement: 生成失败归一化为工具失败

当图片生成调用失败（端点错误、超时、响应不合法）时，`generate_image` SHALL 返回明确的失败结果交由 AI 处理，MUST NOT 让异常中断主循环。

#### Scenario: 生成失败返回失败结果
- **WHEN** images 端点调用失败或超时
- **THEN** `generate_image` 返回明确的失败说明结果，主循环不崩溃、可继续

