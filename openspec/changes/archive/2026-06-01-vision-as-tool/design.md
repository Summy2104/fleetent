## Context

AR21(`multimodal-input`,已归档)的 `_select_route(messages)`:`has_image_block(messages)` 为真则走 `vision` 路由、否则 `default`。逐轮判定 → 上下文一旦含图就持续走 vision。`image-generation-tool`(已归档)确立了"工具产物存盘 + 返回短引用、绝不回 base64"模式(`GENERATED_DIR` 可注入路径常量、`_save_image`、`generate_image` async `@tool` 经 `_safe_dispatch` await)。`skill-read-on-demand`(已归档)确立了 read-on-demand:重负载内容蒸馏成可发现的引用,模型按需经工具拉取。

本 change 把这套用到视觉:感知(VLM)与推理+行动(文本模型)解耦,视觉变成工具。

约束(CLAUDE.md):TDD Hard Gate;禁止 AI 框架;外部服务必须可自托管(VLM 走自托管 OpenAI 兼容,禁云托管专有);禁止全局可变状态(uploads 路径常量可 monkeypatch);新模块结构 import→常量→数据类→函数;mypy strict;行长 100;LLM/HTTP 测试 mock,目录隔离 tmp_path。

## Goals / Non-Goals

**Goals:**
- 主 agent loop 始终跑文本+工具模型;视觉作 `analyze_image(ref, instruction)` 工具按需调用。
- 入站图片存盘,主上下文只带引用,base64 不进主上下文、不进 trace。
- 含图消息首次自动抽取一次 + 剥离图片块 → 回落文本路由,根除"出过图就一直按 vision 计费"。
- VLM 端点自托管 OpenAI 兼容;未配置时优雅失败。

**Non-Goals:**
- 不改 AR21(其 `_select_route`/`has_image_block`/图片块结构复用,不修改)。
- 不引入云托管 VLM。
- 不做纯视觉迭代任务(持续盯图改标注)的专门模式。
- 不做多图并发抽取优化(首版逐图)。

## Decisions

### D1:视觉作工具,主循环跑文本模型(反转关系)
`analyze_image(ref, instruction) -> str`:内部 `vision_client.analyze(image_bytes, instruction)` 对自托管 VLM 端点做一次 vision chat 调用,返回结构化文本。主 agent loop 不再因含图切到 vision 模型——图被工具消化为文本后,`_select_route` 自然回 default。
**为何**:文本编排用最强文本模型、感知用最强 VLM,各自独立选;省 token;天然支持多图/回看/对比;与 tool 中心架构一致。
**Alternatives**:保持 AR21 逐轮 vision 路由——被否(编排落在视觉模型、重复计费、上下文肿)。

### D2:入站图片存盘 + 引用(对称 image-gen)
新增 `tools.UPLOADS_DIR`(默认 `data/uploads`,可注入)。入站图片写盘,主上下文携带引用(路径)。`analyze_image` 按引用从盘读图。base64 绝不进主上下文/trace。
**为何**:对称 `GENERATED_DIR` 既有模式;base64 出主上下文,前缀缓存与 context 都受益;引用可被多次 `analyze_image`(回看)复用。

### D3:首次自动抽取 + 剥离图片块(normalizer)
含图消息进 normalizer 时,自动先跑一次 `analyze_image`(instruction=用户文本),注入文本结果;并把该图片块从将要持久化/送模型的消息中剥离、替换为盘上引用。
**为何**:首眼自动(无冷启动延迟、无需模型先想到要看);剥离后上下文不再含图 → 路由回落 default、不再逐轮按 vision 计费。后续回看由模型主动调工具(read-on-demand)。
**Alternatives**:纯按需(不自动首跑)——被否(模型可能不主动调,首眼有延迟感);倾向自动首跑。**Open Question**:是否保留少量场景纯按需,见下。

### D4:VLM client 对称 image_gen_client,自托管 OpenAI 兼容
`vision_client.analyze` 用 `AsyncOpenAI(base_url=vision_url)` 发 vision chat(image_url/base64 块 + instruction 文本),取回文本;`VisionError`;自托管端点常忽略 auth → 占位 api_key。config 加 `vision_url`(默认空)/`vision_model`。
**为何**:与 `image_gen_client` 同构,self-hostable,符合数据主权;默认空 + 优雅失败同 image-gen。

## Risks / Trade-offs

- [首次自动抽取多一次 VLM 调用的延迟] → 可与"本就要处理的首轮"合并;抽取结果缓存在对话里,后续不重复抽取。
- [抽取保真度:首次抽取可能漏细节] → 模型可按需 `analyze_image` 回看补;比"整张图每轮重发给未必擅长编排的模型"更可控、可 log。
- [剥离图片块改变消息持久化形态] → 复用 run() 就地修改契约(messages[:]);剥离后存的是"引用+抽取文本",session 不带 base64(更干净)。
- [自托管 VLM 端点能力/格式差异] → client 走标准 OpenAI 兼容 vision 消息;端点未配/失败优雅降级为错误文本。

## Open Questions

- 首次自动抽取 vs 纯按需:倾向**自动首跑**(D3);是否给某些场景(如纯转发图片不需理解)留纯按需开关,待实现时按最小改动定。
- 抽取后是否**完全剥离**原图 base64(只留盘上引用)还是保留一轮:倾向**完全剥离**(只留引用),回看走 `analyze_image`;若发现模型频繁需要原图可再评估。
- uploads 图片的生命周期/清理:是否纳入 session 维护触发器(对称 session 清理)——本 change 先存盘,清理留后续。
