## ADDED Requirements

### Requirement: 提供文生图工具 generate_image

平台 SHALL 提供一个 `generate_image` 工具，注册到工具注册表，供 AI 在对话中调用以从文本 prompt 生成图片。该工具 MUST 以 `low` 风险级别注册，因而 MUST NOT 触发人工审批门。

#### Scenario: AI 调用 generate_image 生成图片
- **WHEN** AI 在工具调用中请求 `generate_image` 并提供 prompt
- **THEN** 工具被 dispatch 执行，生成一张图片并返回结果，循环继续

#### Scenario: low 风险不触发审批
- **WHEN** `generate_image` 被调用
- **THEN** 不经过人工审批门，直接执行（与其它 low 风险工具一致）

### Requirement: 后端为自托管 OpenAI 兼容 images 端点

图片生成 SHALL 调用由配置指定的、OpenAI 兼容的 images 端点（`/v1/images/generations`），端点 MUST 可自托管、数据不出内网。平台 MUST NOT 调用云托管专有图像服务（如 DALL·E / Midjourney）。

#### Scenario: 经配置的自托管端点生成
- **WHEN** `generate_image` 执行且已配置 `image_gen_url`
- **THEN** 经该 OpenAI 兼容端点生成图片，图片数据不出内网

#### Scenario: 未配置端点时明确失败
- **WHEN** `generate_image` 执行但未配置可用的 images 端点
- **THEN** 工具以明确错误结果返回（不静默成功），不崩溃主循环

### Requirement: 生成图存盘并返回短引用

生成的图片 SHALL 保存到数据目录，工具返回值 MUST 为指向该图片的短引用（路径或 id），MUST NOT 将图片 base64 内联进工具结果。生成图的 base64 数据 MUST NOT 进入对话上下文或运行日志（trace）。

#### Scenario: 返回引用而非 base64
- **WHEN** `generate_image` 成功生成一张图片
- **THEN** 工具结果为指向已存盘图片的短引用，结果中不含 base64 图片数据

#### Scenario: trace 不含生成图 base64
- **WHEN** 一次含 `generate_image` 调用的运行写入 trace
- **THEN** trace 中不含生成图的完整 base64 串

### Requirement: 生成失败归一化为工具失败

当图片生成调用失败（端点错误、超时、响应不合法）时，`generate_image` SHALL 返回明确的失败结果交由 AI 处理，MUST NOT 让异常中断主循环。

#### Scenario: 生成失败返回失败结果
- **WHEN** images 端点调用失败或超时
- **THEN** `generate_image` 返回明确的失败说明结果，主循环不崩溃、可继续
