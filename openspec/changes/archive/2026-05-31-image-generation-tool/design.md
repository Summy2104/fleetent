## Context

fleetent 的能力分两层接入：主循环的 LLM 调用走 `model_router`（task_type → OpenAI 兼容 chat provider）；带副作用 / 有产物的能力走 `@tool` 工具（`tools.py` import 副作用注册，`tool_registry.dispatch` 执行，`run()` 经 `_safe_dispatch` 调用并 await 协程结果）。

文生图（text-to-image）是「文本 → 图」的输出型操作，调用的是 **images 端点**而非 chat completions，产出图片产物。它不符合主循环的 chat 形态，但完美契合工具机制：AI 判断意图 → 调 `generate_image` → 产出并返回引用 → 循环继续。这与 AR21（视觉输入，图 → chat → 文本）是相反方向、不同 API 的两件事，故 AR21 走 `vision` task_type 路由，本能力走工具。

约束（CLAUDE.md）：基础设施须可自托管（SD/ComfyUI/Flux 符合，DALL·E/Midjourney 云托管禁止）；禁止 AI 框架；禁止全局可变状态（`GENERATED_DIR` 可 monkeypatch）；新模块结构 import → 常量 → 数据类 → 函数；mypy strict；TDD Hard Gate；外部 HTTP 测试用 mock。

## Goals / Non-Goals

**Goals:**
- 提供 `generate_image` 工具（`@tool(risk_level="low")`），AI 可在对话中调用。
- 经自托管、OpenAI 兼容的 images 端点生成图片。
- 生成图存盘并返回短引用，**绝不把 base64 内联进 tool_result / 上下文 / trace**。
- 后端 endpoint 经 Settings 配置；数据不出内网。

**Non-Goals:**
- 不实现把生成图投递回 IM / HTTP 用户（属 im_gateway / server 下游）。
- 不实现异步任务队列 / 进度回传（v1 同步 + 超时；异步为远期）。
- 不实现图片编辑 / inpainting / 图生图（image-to-image）等其它图像操作。
- 不实现生成图的清理 / 配额（可后续与 session-disk-management 协调）。
- 不改动主循环、model_router、终止框架。

## Decisions

### D1：文生图做成工具，不做 chat task_type
`generate_image` 经 `@tool(risk_level="low")` 注册到 `tool_registry`，由 AI 决定调用时机。
**为何**：images 端点与 chat completions 是不同 API，产出产物而非对话消息；工具机制（dispatch + `_safe_dispatch` await）天然支持，主循环零改动。把它塞进 model_router 会让「路由 chat 模型」的抽象漏水。
**Alternatives**：①作为 model_router 的一个 task_type——被否，调用形态（images vs chat）不同，路由抽象不成立；②在主循环特判生成意图——被否，意图识别正是 LLM + 工具调用要解决的，不该硬编码进循环。

### D2：后端为自托管 OpenAI 兼容 images 端点
新增 `image_gen_client.py`，用 `AsyncOpenAI(base_url=settings.image_gen_url, ...)` 调 `images.generate(model=..., prompt=..., response_format="b64_json")`，从响应取 `b64_json` 解码为 bytes 返回。
**为何**：复用 model_router 既有的「OpenAI 兼容 + base_url 指向任意自托管端点」哲学，零新依赖；SD-WebUI / ComfyUI / Flux 等可经兼容层暴露该端点，满足自托管与数据主权。
**Alternatives**：①各后端原生 API（SD-WebUI 的 `/sdapi`、ComfyUI 的图工作流 API）直连——被否，每种后端一套 adapter，维护成本高；统一要求暴露 OpenAI 兼容端点（用户已确认）后只需一个客户端。②云托管 images（DALL·E）——被否，违反数据主权（CLAUDE.md 永久禁止）。
**Open**：`response_format` 是否所有自托管兼容端点都支持 `b64_json`（部分只回 url）——实现首步核实，若回 url 则客户端再 fetch bytes（同样要求该 url 在内网可达）。

### D3：存盘 + 返回引用，绝不内联 base64
- 生成 bytes 保存到 `GENERATED_DIR / f"{id}.png"`（`GENERATED_DIR` 模块级常量，默认 `data/generated/`，可 monkeypatch）。`id` 用调用方/工具内生成的唯一标识（避免 `Math.random`/时间依赖问题——用 uuid4）。
- 工具返回值为**短文本引用**（如 `图片已生成：data/generated/{id}.png`），进入 tool_result。
**为何**：images 响应里的 base64 极长，若作为 tool_result 会重蹈 AR21 Q2 的覆辙——污染 token 估算与 trace、撑爆 JSONL。存盘 + 引用让上下文只留一个短串。与 AR21 D3「base64 不进内部记账」同源。
**Alternatives**：返回 base64 给 LLM——被否，多数 chat 模型也不需要看生成图的像素，只需知道「已生成 + 在哪」；确需后续视觉分析时由 AR21 路径按引用重新加载（后续工作）。

### D4：风险级别 low（不触发审批）
`@tool(risk_level="low")`——按用户决定，生成图片不需人工审批，走普通 dispatch 路径。
**为何**：生成是常规、低破坏性操作；medium/high 才触发 permission_gate。若未来需对算力成本设限，由预算管控（AR18）统一处理，不在工具风险级别上做。

### D5：同步 + 超时（v1）
v1 工具内同步 await images 调用，设较长超时（生成可能数秒至分钟级）。
**为何**：简单、契合现有同步工具模型；异步任务队列是更大工程，留远期。待波次 2「工具超时保护」落地后，本工具的超时纳入统一机制（design 标注协调点）。

## Risks / Trade-offs

- [自托管端点不支持 `b64_json` 只回 url] → 客户端兼容两种 response_format：优先 b64_json，回 url 时在内网 fetch bytes；实现首步核实后端能力。
- [base64 意外泄漏进 trace/上下文] → 工具返回值仅为短引用，bytes 直接落盘；加用例断言 tool_result 不含 base64、trace 不含 base64。
- [生成耗时长阻塞循环] → v1 同步 + 超时；超时按工具失败返回（与 `_safe_dispatch` 归一化一致），不崩溃循环；异步留远期。
- [生成图无限堆积占满磁盘] → 本次不做清理（Non-Goals）；标注后续与 session-disk-management / 配额协调。
- [GENERATED_DIR 写入与测试污染 data/] → 路径常量可 monkeypatch，测试隔离到 tmp_path（同项目 SQLite/SESSIONS_DIR 隔离惯例）。

## Open Questions

- 自托管兼容端点的 `response_format` 支持情况（b64_json / url）——实现首步用目标后端核实，决定客户端解码路径。
- `generate_image` 入参除 prompt 外是否暴露 size / n / model 等——v1 先 prompt + 可选 size，其余用后端默认；按实际后端能力定。
- 生成图引用的形态（相对路径 / 平台内 URL / id）——v1 用相对路径字符串；若后续要投递给 IM，再约定平台内可解析的引用格式（与 im_gateway 协调）。
