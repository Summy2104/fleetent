## 1. 前置核实(无代码改动)

- [x] 1.1 核实 AR21 复用点:`multimodal.has_image_block` / 图片块结构(`type=="image_url"`)/ `agent_loop._select_route`(含图→vision、否则 default),确认"剥离图片块后路由自然回 default"成立
- [x] 1.2 核实 image-gen 复用模式:`tools.GENERATED_DIR` 可注入路径常量 + `_save_image` + `generate_image` async `@tool` 经 `_safe_dispatch` await + "返回引用不回 base64";`image_gen_client` 结构与 config 形态(`image_gen_url` 默认空、优雅失败)
- [x] 1.3 核实 normalizer 注入链(已是 read-on-demand:base+catalog→memory)与 run() 就地修改契约(`messages[:]`),确定"首次抽取 + 剥离图片块"的插入点

## 2. 自托管 VLM client

- [x] 2.1 Write failing tests for `vision_client.analyze(image_bytes, instruction, *, settings)`:mock HTTP/SDK,断言对自托管 OpenAI 兼容 vision 端点发出含图片块+instruction 的请求、返回文本;端点未配置(`vision_url` 空)抛 `VisionError`。运行 `uv run pytest -x -q` 看到红
- [x] 2.2 Implement:新建 `src/fleetent/vision_client.py`,`AsyncOpenAI(base_url=vision_url)` 发 vision chat、取回文本,`VisionError`,占位 api_key;config 加 `vision_url=""` / `vision_model="default"`。看到绿

## 3. uploads 存盘 + 引用

- [x] 3.1 Write failing tests:`tools.UPLOADS_DIR` 可 monkeypatch;存盘函数把图片字节写入 uploads 目录并返回短引用(路径);引用可据以读回字节。uploads 目录隔离到 `tmp_path`。看到红
- [x] 3.2 Implement:`tools.UPLOADS_DIR`(默认 `data/uploads`,可注入)+ 存盘/取盘助手(对称 `_save_image`),返回引用、读回字节。看到绿

## 4. analyze_image 工具

- [x] 4.1 Write failing tests for `analyze_image(ref, instruction)`(经 `tool_registry.dispatch` / `_safe_dispatch`,async):有效引用→调 client→返回结构化文本、**结果不含 base64**;无效引用→明确错误文本(不抛);`vision_url` 空→明确未配置失败文本(不抛、不中断)。HTTP/SDK mock。看到红
- [x] 4.2 Implement:`analyze_image` `@tool`:按 ref 读盘上图→`vision_client.analyze`→返回文本;无效 ref / 未配置 / 调用失败→对应错误文本。看到绿
- [x] 4.3 守卫测试:trace 中 `analyze_image` 工具结果消息不含 base64(对称 image-gen 的 no-base64 守卫)

## 5. normalizer 首次自动抽取 + 剥离图片块

- [x] 5.1 Write failing tests:含图片块的入站消息经 normalizer → (a) 图片字节写入 uploads、(b) 自动调用一次 `analyze_image`(以用户文本为 instruction)、(c) 注入抽取文本、(d) 图片块被替换为盘上引用、(e) 交给 run() 的 messages 不再含 image_url 块 → `_select_route` 回 default。`analyze_image`/VLM mock,目录隔离。看到红
- [x] 5.2 Implement:normalizer 检测 `has_image_block` → 存盘 + 首次 `analyze_image` + 注入文本 + 剥离图片块为引用;保持 run() 就地修改契约。看到绿
- [x] 5.3 守卫测试:抽取后后续轮上下文无图片块、路由回 default;模型可再次 `analyze_image(ref, 新 instruction)` 回看(工具仍能据引用读图)

## 6. 收尾

- [x] 6.1 全量 `ANTHROPIC_API_KEY=... uv run pytest` 通过,无回归;AR21 既有 vision 路由用例不破(图未被剥离的纯 run/run_stream 路径仍按 has_image_block 选路由)
- [x] 6.2 我的文件 `uv run ruff format && ruff check` 全绿;`uv run mypy src` 不新增错误模式
- [x] 6.3 验收对照 spec 三需求:analyze_image 按需理解(含无效引用/未配置降级)、入站图片存盘只带引用、含图首次自动抽取+剥离+回落文本路由
