## 1. 前置核实（实现前的事实确认，无代码改动）

- [ ] 1.1 核实 `openai` SDK 的 `AsyncOpenAI.images.generate` 签名与响应结构（`b64_json` vs `url`、`response_format` 支持），据此定 `image_gen_client` 的解码路径（b64 优先，必要时回 url fetch）
- [ ] 1.2 核实 `@tool` 装饰器与 `tool_registry.dispatch`：async 工具如何被 `run()._safe_dispatch` await；low 风险不经 permission_gate（agent_loop 审批分支只对 medium/high 生效）
- [ ] 1.3 确认 `config.py` 的 `Settings` 新增 `image_gen_url`（+ 可选 `image_gen_model`）字段的方式（类比 `microsandbox_url`）；确认数据目录约定，定 `GENERATED_DIR` 默认值（`data/generated/`）与 monkeypatch 注入点

## 2. 配置与存储路径

- [ ] 2.1 Write failing tests：`Settings` 含 `image_gen_url`（与可选 `image_gen_model`）字段；`GENERATED_DIR` 模块级常量存在且可 monkeypatch。看到红
- [ ] 2.2 Implement：`Settings` 新增字段；定义 `GENERATED_DIR` 常量。看到绿

## 3. 图片生成客户端（image_gen_client.py）

- [ ] 3.1 Write failing tests for `generate(prompt, ...) -> bytes`：mock OpenAI 兼容 images 端点（respx / mock AsyncOpenAI），b64_json 响应被解码为原始图片 bytes；端点错误抛出可识别异常。**不发真实请求**。看到红
- [ ] 3.2 Implement `image_gen_client.generate()`（`AsyncOpenAI(base_url=image_gen_url)` 调 images.generate，解码 b64_json；兼容 url 形态）。看到绿

## 4. 存盘 + 返回引用

- [ ] 4.1 Write failing tests：给定图片 bytes，保存到 `GENERATED_DIR/{uuid}.png`（monkeypatch 到 tmp_path），返回短引用字符串；**断言返回值与落盘路径均不含 base64**。看到红
- [ ] 4.2 Implement 存盘辅助（uuid4 命名，写 bytes，返回引用）。看到绿

## 5. generate_image 工具

- [ ] 5.1 Write failing tests：`generate_image(prompt)` 注册为工具（`get_schemas()` 含之，risk_level=low）；成功路径返回短引用（mock client + GENERATED_DIR）；端点失败/超时 → 返回明确失败结果而非抛出（归一化为工具失败）。看到红
- [ ] 5.2 Implement `generate_image`（`@tool(risk_level="low")`，调 client → 存盘 → 返回引用；捕获失败归一化为失败结果文本）。看到绿
- [ ] 5.3 Write failing tests 守卫：含 `generate_image` 结果的 messages 经 `eval_logger._serialize` / 进入 trace 不含 base64（引用即短串，天然满足；守卫防回归）。看到红（若已绿说明天然满足，保留为回归守卫）
- [ ] 5.4 Implement / 确认使守卫通过。看到绿

## 6. 收尾

- [ ] 6.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`），无回归
- [ ] 6.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿
- [ ] 6.3 `uv run mypy src` 无新增错误模式
