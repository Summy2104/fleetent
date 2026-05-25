## 1. webhook_router — 配置加载与 payload 处理

- [x] 1.1 Write failing tests: 从 YAML 加载 source 列表；缺失文件返回空列表；`extract_message(template, payload)` 模板替换成功；字段缺失时 fallback 到 json.dumps
- [x] 1.2 新建 `webhook_router.py`：`load_sources(path) -> dict[str, WebhookSource]`（dataclass：id, secret, user_id, agent_name, message_template）；`extract_message(template, payload) -> str`

## 2. webhook_router — 签名验证

- [x] 2.1 Write failing tests: 正确签名返回 True；错误签名返回 False；无 secret 配置时始终返回 True；使用 `hmac.compare_digest` 防时序攻击
- [x] 2.2 实现 `verify_signature(secret: str | None, body: bytes, header: str | None) -> bool`

## 3. server.py — webhook 端点注册

- [x] 3.1 Write failing tests: `POST /webhook/known-source` 返回 202；`POST /webhook/unknown` 返回 404；签名错误返回 403；无 secret 配置时无需签名头
- [x] 3.2 在 `server.py` lifespan 中加载 `config/webhooks.yaml`（不存在时跳过），注册 `POST /webhook/{source_id}` 端点；调用 `webhook_router.verify_signature()`；202 立即返回

## 4. server.py — 后台任务派发

- [x] 4.1 Write failing tests: 端点返回 202 后 `normalizer.route()` 被调用一次；`NormalizedMessage.platform == "webhook"`、`session_id == f"webhook-{source_id}"`、`user_id` 来自配置；`reply_func` 调用时无副作用
- [x] 4.2 在端点处理函数中构造 `NormalizedMessage`（no-op reply_func），用 `asyncio.create_task(normalizer.route(msg))` 异步派发

## 5. 配置示例文件

- [x] 5.1 新建 `config/webhooks.example.yaml`，含注释说明各字段用途和签名配置方式

## 6. 验证

- [x] 6.1 运行完整测试套件（`uv run pytest -x -q`），确认全部通过
- [ ] 6.2 手动验证：用 `curl` 发送带 HMAC 签名的 POST 到 `/webhook/{id}`，确认 202 响应且 eval trace 中出现对应 agent run 记录
