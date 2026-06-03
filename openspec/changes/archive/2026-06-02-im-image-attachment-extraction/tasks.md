## 1. 前置核实(无代码改动)

- [x] 1.1 核实 normalizer 契约:`_image_attachments` 判据(`(bytes, str-mime 且 image/ 开头)`)与 `NormalizedMessage.attachments` 字段,确认适配器组装 `(bytes, mimetype)` 即触发既有抽取,不需改 normalizer
- [x] 1.2 核实 slack handler 现状(`event.get("files")` 字段、`url_private` / `mimetype`、硬编码 `attachments=[]`)与 telegram handler 现状(只注册 `filters.TEXT & ~filters.COMMAND`、硬编码 `attachments=[]`、text 取 `update.message.text`)

## 2. Slack 适配器抽图

- [x] 2.1 Write failing tests:`handle_message` 含 `image/*` file → httpx mock 下载 `url_private`(断言带 `Authorization: Bearer {bot_token}`)→ 传给 route 的 `NormalizedMessage.attachments` 含 `(bytes, mimetype)`;非图 file 被忽略;无 files → 空 attachments;下载失败 → 空 attachments 不崩(记 warning)。route 用 AsyncMock。运行 `ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -x -q` 看到红
- [x] 2.2 Implement:`slack.py` `handle_message` 读 `event.get("files")`,对 `mimetype` 以 `image/` 开头的 file 用 `httpx.AsyncClient` GET `url_private`(`Authorization: Bearer {bot_token}`)取 `response.content`,组装 `attachments`(替换硬编码 `[]`);逐附件 try/except,失败 `logger.warning` 跳过。看到绿

## 3. Telegram 适配器抽图

- [x] 3.1 Write failing tests:handler 处理 photo 消息 → mock `context.bot.get_file` + `download_as_bytearray` → attachments 含 `(bytes, "image/jpeg")`;text 取 `caption`;纯文本消息 attachments 空、text 取 `text`、行为不变;下载失败 → 空 attachments 不崩(记 warning);`create_app` 注册的 handler filter 含 photo。看到红
- [x] 3.2 Implement:`telegram.py` MessageHandler filter 改为也接收 photo(`(filters.TEXT | filters.PHOTO) & ~filters.COMMAND`);`handle_message` 取 `update.message.photo` 最大一张 → `await context.bot.get_file(file_id)` → `await file.download_as_bytearray()` → 组装 `attachments=[(bytes(ba), "image/jpeg")]`;text 改 `caption or text or ""`;失败 `logger.warning` 降级空 attachments。看到绿

## 4. 收尾

- [x] 4.1 全量 `ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -q` 通过,无回归(基线 1391 passed);纯文本 IM 行为不变;含图→attachments 含 `(bytes, image/*)`
- [x] 4.2 我改/建文件 `uv run ruff format && ruff check` 全绿;`uv run mypy src` 不新增错误模式(slack.py/telegram.py 既有 `Settings()` call-arg 为基线)
- [x] 4.3 确认未改 normalizer 抽取逻辑、connector config/registry/allowlist、session 派生、reply_func、im_user_store
- [x] 4.4 在 `docs/capabilities/wave2-apply-decisions.md` 末尾追加 `## [follow-up] im-image-attachment-extraction` 记跨域风险(与张亮 im-gateway-management 同改 slack.py/telegram.py,不同关注点)+ 实现要点
- [x] 4.5 `openspec validate im-image-attachment-extraction --strict` 通过
