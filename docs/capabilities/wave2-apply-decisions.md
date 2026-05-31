# Wave-2 Apply 决策日志

> 全自主 apply 期间,遇到的冲突 / Open Question 及其解决记录,供 zy 最后核实。
> 每个 change 一节:遇到什么、怎么解的、影响。

## vision-as-tool — feat/vision-as-tool

**前置核实结论(tasks 1.x):**
- AR21 复用点确认:`multimodal.has_image_block` 按 `block.get("type") == "image_url"` 判定;`agent_loop._select_route` 仅当 `has_image_block` 为真才走 `vision`,否则 `default`。因此"剥离图片块(主上下文只留盘上引用字符串)→ 路由自然回 default"成立,且**无需改 `_select_route`**。
- image-gen 复用模式确认:`tools.GENERATED_DIR` 是可注入模块级路径常量;`_save_image(data)->ref`(写 `{uuid}.png` 返回路径,绝不回 base64);`generate_image` 是 `@tool(risk_level="low")` async,经 `_safe_dispatch` await;`image_gen_client.generate` 用 `AsyncOpenAI(base_url=..., api_key="image-gen")`、`image_gen_url` 默认空、未配抛 `ImageGenError`、工具层归一化为 `error:` 文本不抛。
- normalizer 注入链确认:`route()` 在 `session_lock` 内组装 system(base+catalog→memory)后 `history.append({"role":"user","content": msg.text})`,再 `await agent_loop.run(history)`,run 就地改 history 后 `session_mgr.save`。**首次抽取的插入点**就是这条 user-append:把"取 msg.text 当 content"换成"先抽取图片再构造 content"。

**实现:**
- 新增 `src/fleetent/vision_client.py`:`analyze(image_bytes, instruction, *, settings) -> str`,对称 `image_gen_client`——`AsyncOpenAI(base_url=settings.vision_url, api_key="vision")` 占位 key,发标准 OpenAI 兼容 vision chat(text 块 + image_url base64 data URL 块),取回 `choices[0].message.content`;`VisionError`;`vision_url` 空抛 `VisionError`;端点错/空 choices/空 content 均抛。
- `config.py`:加 `vision_url=""` / `vision_model="default"`(对称 image_gen 字段,带注释)。`.env.example` 同步加 `VISION_URL=` / `VISION_MODEL=default` 注释。
- `tools.py`:加 `UPLOADS_DIR`(默认 `data/uploads`,可注入)+ `_MIME_EXT` 映射 + `_save_upload(data, mime)->ref`(写 `{uuid}.{ext}`、返回路径)/ `_read_upload(ref)->bytes`;新增 `analyze_image(ref, instruction)` `@tool(risk_level="low")` async:`_read_upload` 失败→`error:` 文本,`VisionError`→`error:` 文本,均不抛(经 `_safe_dispatch` await)。
- `im_gateway/normalizer.py`:新增 `_image_attachments`(从 `msg.attachments` 挑出 `(bytes, mime)` 图片项)+ `_build_user_content(msg)`(无图→原 `msg.text`;有图→逐图 `_save_upload` + 一次 `vision_client.analyze`(instruction=用户文本)→ 把"用户文本 + `[图片 {ref}]\n{分析}`"拼成纯字符串 content)。`route()` 的 user-append 改调它。base64 从不进 history,故 `has_image_block` 天然为假、路由回 default、run 就地改 history 契约不变(content 仍是 str)。

**自解冲突:**
1. **attachments 形态未在 spec/现实中定义**:`NormalizedMessage.attachments` 字段早已存在但所有 caller 传 `[]`,无既定结构。据 `build_message_with_images` 的既有契约(`list[tuple[bytes, mime]]`)定为同形——`_image_attachments` 只收 `(bytes, str)` 且 mime 以 `image/` 打头的项,非图片项忽略。slack/telegram 适配器抽图入 attachments 不在本 change 范围(仍传 `[]`),不动它们。
2. **"剥离图片块"的落地形态**:AR21 的 normalizer 路径其实从没把图片做成 image_url 块进 history(它只 append `msg.text` 字符串)。所以本 change 不是"先建块再剥离",而是**首次抽取直接产出纯文本 content(用户文本 + 引用 + 分析),图片 base64 根本不进主上下文**——等价于 D3 的"剥离后只留引用",且更彻底。run/run_stream 的 `images=` 参数路径(AR21 真正会建 image_url 块的入口)保持不变,其 `_select_route` 仍按 has_image_block 选 vision,AR21 用例不破。
3. **bare `@tool` 对 async 函数报 mypy `type-var`(新错误类型)**:`tool` 的 bare overload 绑定 `F: Callable[..., str]`,async 函数返回 Coroutine 违反 bound → `type-var`(既有 async 工具用的是 `@tool(risk_level=...)` 参数化 overload,只报 `arg-type`)。改用 `@tool(risk_level="low")`(analyze_image 是只读、低风险,与 generate_image 对称),把新 `type-var` 收敛回既有的 `arg-type` 模式。
4. **vision_client `messages=` 的 mypy TypedDict 报错**:dict 字面量精确类型与 OpenAI 的 ChatCompletionMessageParam Union 不洁净匹配(`misc`/`list-item`,且 `arg-type` ignore 覆盖不到)。改为先 `content: list[Any]` / `messages: list[Any]` 再传(同 agent_loop 全程用 `list[Any]` 的既有做法),去掉 inline ignore;末行 `getattr` 的 Any 用 `str(text)` 收口 `no-any-return`。
5. **ruff format 误改无关代码**:`ruff format` 把 tools.py 里 AR 既有的 `schedule_task`/`cancel_task`(本就超 100 行/import 顺序问题)一并重排。已手工还原这几行,只留本 change 新增内容。tools.py 现存的 3 个 ruff 错误(E501+I001+F401,均在 schedule_task/cancel_task)是 stash 验证确认的**改动前既有**遗留,非本 change 引入。

**影响:**
- 新增 `vision_client.py`、`tests/test_vision.py`、`tests/test_normalizer_vision.py`;改 `config.py`、`tools.py`、`im_gateway/normalizer.py`、`.env.example`。
- 全量 **746 passed**(基线 728 + 新增 18),无回归;AR21 multimodal/route 用例全绿。
- ruff:我的新建/修改文件 `ruff format` + `ruff check` 全绿;tools.py 的 3 个 ruff 错误为既有遗留(未触碰)。
- mypy:`uv run mypy src` 总数 base 71 → 本 change 73(+2,编排者实测更正子 agent 误记的"79→73"),无新增**错误模式**——新增 2 个均为既有模式实例:`vision_client.py:53` 的 `Settings()` call-arg 同 `image_gen_client.py`/`server.py`/`im_connector_config.py` 既有;`tools.py` analyze_image 的 `arg-type` 同 generate_image/run_code 既有 async-`@tool` 模式。符合"不新增错误模式"。

**需 zy 核实:**
1. `attachments` 形态定为 `list[tuple[bytes, mime]]`(自解冲突 #1):是否认可。本 change 未让 slack/telegram 适配器真正抽图入 attachments(仍 `[]`),即"入站图片自动抽取"在 IM 端尚无真实数据源——是否需要后续 change 补适配器抽图,还是本 change 应一并接上。
2. 首次抽取直接产出纯文本 content(不经 image_url 块,自解冲突 #2):是否认可这一"比剥离更彻底"的落地,即 IM 路径的图永不以 base64 块进 history。
3. uploads 生命周期/清理本 change 未实现(按 design Open Question 既定:只存盘,清理留后续)。
