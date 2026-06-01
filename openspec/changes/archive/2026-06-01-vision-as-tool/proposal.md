## Why

AR21(`multimodal-input`,已归档)让图片能进 agent:含图片块的消息触发 `_select_route` 走 `vision` 路由。但它是"**逐轮按上下文有没有图片块路由**"——一旦上下文里出现过图片,后续每一轮只要那个 base64 块还在历史里,就持续走 vision 模型。三个硬伤:

- **最难的活落在最不擅长的模型上**:用户上传图片往往不是"识别一下"就完,而是**基于图片内容做后续业务操作**(读发票→填 CRM、读报错截图→开工单)。这些多步、工具密集的编排被钉在 vision 模型上,而视觉模型通常工具调用/复杂推理弱于同级文本模型,且更贵。
- **base64 每轮重发、重复按 vision 计费**:图片块留在上下文,逐轮重新发给模型、重新按视觉计费;第一轮就该"看懂"的图被重复处理多次。
- **base64 撑肿上下文**:挤占真正要带的业务上下文。

本质问题:**感知**(看懂图,一次性、视觉)与**推理+行动**(多步、工具密集、强文本模型)是两种任务,被绑死在同一模型/同一路由上了。

## What Changes

反转关系,与 `skill-read-on-demand` 同一套 read-on-demand / 工具中心哲学:**主 agent loop 始终跑在强文本+工具模型上;视觉作为它可调用的工具。**

- 新增 `analyze_image(ref, instruction) -> text` 内置工具:内部对自托管 VLM 端点做一次聚焦调用(带上意图 instruction),返回**结构化文本**;按图片引用(盘上路径)取图,不在工具结果里回 base64。
- 新增自托管 VLM client(OpenAI 兼容 vision 端点,对称 `image_gen_client`),self-hostable。
- 新增 **uploads 存盘 + 引用**机制(对称 `image_gen` 的 `GENERATED_DIR`):入站图片写盘,主上下文只带短引用。
- `im_gateway/normalizer` 在消息含图时**首次自动抽取**:先跑一次 `analyze_image`(用用户那句话当 instruction),把结构化结果作为消息注入;**抽取后把图片块从主上下文剥离、换成盘上引用** → `_select_route` 自然回落 `default`(文本路由)。后续"回看/对比"由模型主动再调 `analyze_image`。

## Capabilities

### New Capabilities
- `vision-as-tool`: 图像理解以 read-on-demand 工具方式提供——主 agent loop 跑文本模型,`analyze_image(ref, instruction)` 工具按需对自托管 VLM 做一次聚焦调用返回结构化文本;入站图片存盘、主上下文只带引用;含图消息首次由 normalizer 自动抽取一次并剥离图片块,使主循环回落文本路由、不再逐轮按 vision 计费。

### Modified Capabilities
<!-- AR21 multimodal-input 已归档、不改(仍是多模态输入的最小地基:含图→vision 路由)。本 change 是其后继,新增"图片经工具按需理解"这一上层能力,不修改 AR21 的既有需求。 -->

## Impact

- **代码**:
  - 新增 `src/fleetent/vision_client.py`:`analyze(image_bytes, instruction, *, settings) -> str`(`AsyncOpenAI(base_url=vision_url)` 调 chat/completions vision 消息,返回文本),`VisionError`。
  - `tools.py` 新增 `UPLOADS_DIR`(默认 `data/uploads`,可注入)+ `analyze_image(ref, instruction)` `@tool`(async,经 `_safe_dispatch` await):按 ref 读盘上图 → 调 client → 返回结构化文本;ref 无效/端点未配置 → 明确错误文本(不崩、不中断 loop)。
  - `im_gateway/normalizer.py`:含图消息首次自动 `analyze_image`,注入抽取文本,剥离图片块为盘上引用。
  - `config.py`:加 `vision_url=""` / `vision_model="default"`。
- **配置**:`vision_url` 默认空,未配时 `analyze_image` 返回明确失败文本(同 image-gen 形态)。
- **测试**:`vision_client`(mock HTTP)、`analyze_image`(找到/未找到 ref、未配置端点、结果不含 base64)、normalizer(含图→首次抽取+剥离+回落 default 路由)。LLM/HTTP mock,uploads 目录隔离 `tmp_path`。
- **不影响**:AR21 的 `_select_route`(仍按 has_image_block 选路由——图被剥离后自然回 default)、文本路径、`image_gen`。
- **Non-Goals**:不实现纯视觉迭代任务的专门模式;不引入云托管 VLM(必须自托管 OpenAI 兼容);不改 AR21。

## Dependencies

- 复用 AR21(`multimodal-input`,已归档)的 `has_image_block` / 图片块结构与 `_select_route`;复用 `image-generation-tool`(已归档)的"存盘+返回引用、绝不回 base64"模式与可注入路径常量风格。
- 与 `skill-read-on-demand`(已归档)同一 read-on-demand 哲学(重负载内容蒸馏成文本/引用再进循环,模型按需经工具拉取)。
