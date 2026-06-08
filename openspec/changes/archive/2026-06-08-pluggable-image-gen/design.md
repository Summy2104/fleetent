## Context

`image_gen_client.py`（107 行）是单一模块，调用 `AsyncOpenAI.images.generate()`，硬编码走 `/v1/images/generations`，对应 `agent.yaml` 的 `protocol: openai_image_generation`。

Gemini 图像模型（如 `gemini-3-pro-image-preview`）在 NewAPI 等兼容代理上只能通过 Chat Completions API（`/v1/chat/completions`）调用——模型在响应 content 里以 `data:image/jpeg;base64,...` 或裸 URL 形式返回图像，不支持 `/v1/images/generations`。

现有协议模型：`ModelTarget.protocol` 已经是 `agent.yaml` 到运行时的路由键（`openai_chat`、`openai_image_generation`、`http_embedding`、`http_rerank`），`ResolvedModelConfig` 携带全部连接参数。

## Goals / Non-Goals

**Goals:**
- 引入 `ImageGenProvider` ABC + registry，以 `protocol` 为键派发
- 新增 `openai_image_chat` 协议，走 Chat Completions + base64/URL 提取
- `openai_image_generation` 行为保持 100% 不变（代码迁移，不改逻辑）
- `image_gen_client.py` 对外接口不变（shim）
- 无新外部依赖

**Non-Goals:**
- 支持 FAL、Krea 等非 OpenAI-compatible 后端（需要额外 SDK）
- 流式图像生成
- 多图生成（`n > 1`）
- provider 热加载 / 运行时注册

## Decisions

### D1：以 `protocol` 字段而非独立配置项选择 provider

Hermes 用 `config.yaml` 里的 `image_gen.provider` 选择后端，与模型路由分离。Fleetent 没有全局 config.yaml，所有模型路由由 `agent.yaml` 的 `models.targets[].protocol` 驱动。

**选择：registry 以 `protocol` 字符串为键**，与现有路由机制对齐，无需引入新配置维度。好处：`agent.yaml` 单一来源；坏处：protocol 命名空间承担"协议"和"后端选择"两个语义，但两者在此场景下一一对应，无歧义。

### D2：子包 `tools/image_gen/` 而非同级文件

两个 provider 放同级会污染 `tools/` 顶层。子包边界清晰，日后增加第三个协议只加一个文件。`image_gen_client.py` 变为 shim 保证零破坏兼容。

### D3：api_key 通过 `policy.require_api_key()` 解析后作为参数传入 provider

`ResolvedModelConfig` 只含 `api_key_env` 名称，不含明文 key。在 `image_gen/__init__.py` 的 `generate()` 统一调用 `policy.require_api_key(resolved)` 解析，再以关键字参数 `api_key=` 传给 `registry.dispatch()`，provider 不持有 policy 对象。

### D4：ChatImageProvider 的 base64 提取用 regex

newapi 对 Gemini 图像模型的响应格式是在 content 字符串里嵌入 Markdown `![image](data:image/jpeg;base64,...)` 或直接是 `data:` URI。用 `re.search(r'data:image/(\w+);base64,([A-Za-z0-9+/=\s]+)', content)` 提取，与 northstar 实现一致，覆盖 jpeg/png/webp。裸 URL（`http`/`https` 开头）作为次级 fallback，用 `_fetch_url()` 下载。

## Risks / Trade-offs

- **[Risk] Chat 响应格式无文档保证** → 响应 format 变化时 regex 可能失配，`ChatImageProvider` 在无匹配时抛 `ImageGenError` 并在 message 里包含前 200 字符，便于诊断。
- **[Risk] shim import 与原模块行为完全等价** → 测试用 `is` 检查 shim re-export 的对象与 `image_gen` 包对象是同一对象，防止类型不等问题。
- **[Risk] openai_image_chat 协议的 `base_url` 末尾斜杠** → 交由 `openai.AsyncOpenAI` SDK 处理，与 `openai_chat` 协议一致。

## Migration Plan

1. 新增 `tools/image_gen/` 子包，`image_gen_client.py` 改为 shim——无 API 变化，可独立合并
2. `agent_config.py` 新增协议校验——向后兼容，现有配置不受影响
3. 现有 `openai_image_generation` 配置无需任何修改
4. 使用 `openai_image_chat` 的用户在 `agent.yaml` 增加新 target + route 即可

回滚：删除 `tools/image_gen/`，恢复 `image_gen_client.py` 原内容，删除 `agent_config.py` 新增的协议分支。
