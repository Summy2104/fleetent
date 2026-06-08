## Why

当前 `image_gen_client.py` 硬编码 `openai_image_generation` 协议（`/v1/images/generations`），无法支持通过 Chat Completions 路径工作的图像模型（如 Gemini via NewAPI）。企业客户需要在自托管代理中使用多种图像生成后端，不同模型走不同 API 路径，现有单一协议无法满足需求。

## What Changes

- **新增** `tools/image_gen/` 子包：`ImageGenProvider` ABC、provider registry、`OpenAIImagesProvider`（现有逻辑迁移）、`ChatImageProvider`（新 Chat Completions 路径）
- **新增** `openai_image_chat` 协议：通过 `base_url` + Chat Completions API 调用，从响应 content 中提取 `data:image/...;base64,...` 或裸 URL
- **修改** `agent_config.py`：新增 `openai_image_chat` 协议的校验规则（要求 `base_url` + `model`）
- **修改** `image_gen_client.py`：变为 1 行 re-export shim，保持现有 import 不破坏
- **修改** `image-generation-tool` spec：更新后端描述，增加 `openai_image_chat` 协议要求

## Capabilities

### New Capabilities

- `pluggable-image-gen-backend`: 可插拔图像生成后端系统——provider ABC、registry、两个内置 provider（OpenAI Images API 和 Chat Completions），由 `agent.yaml` 中的 `protocol` 字段驱动选择

### Modified Capabilities

- `image-generation-tool`: 后端不再限于单一 OpenAI Images API，改为支持多协议（`openai_image_generation` 保持不变，新增 `openai_image_chat`）

## Impact

- `src/fleetent/tools/image_gen_client.py`：变为 shim
- `src/fleetent/tools/image_gen/`：新增子包（5 个文件）
- `src/fleetent/agent_config.py`：新增协议校验分支
- `tests/unit/test_image_gen.py`：扩充测试
- 无新外部依赖（复用已有 `openai` SDK）
- 现有 `openai_image_generation` 配置完全向后兼容
