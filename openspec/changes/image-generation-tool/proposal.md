## Why

平台目前只能「看图」（AR21 多模态输入：图 → 模型 → 文本），不能「生成图」（文本 → 图）。企业场景里用户会要求生成示意图、配图、图表草稿等。文生图（text-to-image, T2I）与视觉输入是**两个方向相反的能力**：视觉输入是一次普通的 chat completion（图作为输入内容块），而文生图是调用**不同的 API 端点**产出一个图片产物——它本质是一个带副作用、有产物的「动作」，最契合 `@tool` 工具机制，而非 model_router 的 chat task_type。

因此本 change 新增一个 `generate_image` 工具：由 AI 在对话中判断「用户要生成图」时调用，工具调自托管的 OpenAI 兼容 images 端点生成图片、存盘并返回引用。主循环零改动。

## What Changes

- 新增**文生图工具** `generate_image`（`@tool(risk_level="low")`，注册于 `tools.py`）：入参 prompt（及可选尺寸等），产出一张图片。
- 新增**图片生成客户端**（`src/fleetent/image_gen_client.py`）：调用**自托管、OpenAI 兼容**的 `/v1/images/generations` 端点（复用 `AsyncOpenAI` + `base_url` 的既有哲学），返回图片字节。
- **输出存盘 + 返回引用，绝不内联 base64**：生成的图片保存到数据目录（如 `data/generated/{id}.png`），工具返回**短引用**（路径 / id），而非把 base64 巨串塞进 tool_result——避免污染上下文与 trace（与 AR21 D3 占位原则同源、反方向）。
- **后端可自托管**：端点由 Settings `image_gen_url` 配置（env 可配，类比 `microsandbox_url`）；只对接自托管/OpenAI 兼容服务（Stable Diffusion / ComfyUI / Flux 等暴露兼容端点者），**禁止** DALL·E / Midjourney 等云托管专有服务。
- **v1 同步执行 + 较长超时**；异步任务队列作为远期（标注 Non-Goals）。
- 投递（把生成图发回 IM / HTTP 用户）属 im_gateway / server 的下游工作，本 change 只负责「生成 + 存盘 + 返回引用」。

## Capabilities

### New Capabilities
- `image-generation-tool`: 文生图工具 `generate_image`——AI 可调用以从文本 prompt 生成图片；后端为自托管 OpenAI 兼容 images 端点（数据不出内网，禁云托管专有服务）；生成图存盘并返回短引用，不内联 base64；风险级别 low。

### Modified Capabilities
<!-- 无既有 spec 的需求级行为变更。tools dispatch / 主循环行为不变；本工具按 @tool 机制注册，是加性能力。 -->

## Impact

- **代码**：
  - 新增 `src/fleetent/image_gen_client.py`（OpenAI 兼容 images 端点客户端，返回图片 bytes）。
  - 修改 `src/fleetent/tools.py`：注册 `generate_image` 工具（`@tool(risk_level="low")`，import 副作用注册）。
  - 新增生成图存储辅助（可在 tools.py 内或单独模块）：保存 bytes 到可注入的 `GENERATED_DIR`（默认 `data/generated/`），返回引用。
- **配置**：`config.py` 的 `Settings` 增加 `image_gen_url`（默认指向自托管端点占位）与可选 `image_gen_model`；`GENERATED_DIR` 为模块级路径常量，可 monkeypatch 注入（禁全局可变状态）。
- **依赖**：复用既有 `openai` SDK（`AsyncOpenAI.images.generate`），**无新依赖**；后端服务（SD/ComfyUI/Flux）由部署方自托管，须在 PR 说明自托管方案。
- **测试**：新增 `tests/test_image_gen_client.py` 与 `tests/test_tools.py` 相关用例；images 端点调用用 `respx`/`mock`，**不发真实请求**；`GENERATED_DIR` 隔离到 `tmp_path`。
- **不影响**：主循环、model fallback、终止框架、permission_gate（low 风险不触发审批）、其它工具的既有行为。
