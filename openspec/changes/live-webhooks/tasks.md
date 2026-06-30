## 1. webhook_router 补 reply_target（中立模型）

- [ ] 1.1 写测试(红)：`WebhookSource` 新增 `reply_target: str | None`（默认 None）；`extract_message`/`verify_signature` 行为不回归（HMAC、模板、fallback、无 secret 放行）
- [ ] 1.2 实现(绿)：`webhook_router.WebhookSource` 加 `reply_target` 字段；`load_sources` 解析（标注 YAML 路径废弃，不被 face 调用）

## 2. standalone source 解析（agent.yaml `webhooks.sources`）

- [ ] 2.1 写测试(红)：`config.parse`/`agent_config` 把 `webhooks.sources: [{id,user_id,agent_name?,message_template,reply_target,secret_env}]` 解析为 `WebhookSource` 列表；`secret_env` → 从 env 取 secret；无 sources 时为空
- [ ] 2.2 实现(绿)：`config.py` `WebhooksSettings` 加 `sources`；提供 agent.yaml → `WebhookSource` 的解析（secret 经 `secret_env` 解析）

## 3. standalone 端点 + 派发（agent_app `POST /webhook/{id}`）

- [ ] 3.1 写集成测试(红)：agent_app `POST /webhook/{id}`——未知 source 404；`webhooks` 关 / body 超 `max_body_bytes` 拒；有 secret 时 HMAC 失败 403、成功 202；已知 source → 立即 202 且后台 `normalizer.route()`（`session_id="webhook-{id}"`、以 source.user_id 跑）；reply 默认 no-op（无出站、结果入 trace）
- [ ] 3.2 实现(绿)：`runtime/agent_app.py` 挂 `POST /webhook/{source_id}`（standalone face），查 agent.yaml source → 闸 → `verify_signature` → `extract_message` → 构 `NormalizedMessage` → 202 + 后台 route；**MUST NOT import platform**（层守护）

## 4. managed source 存储（Alembic 表 + store）

- [ ] 4.1 写集成测试(红)：Alembic 迁移建 `webhook_sources`（id/agent_name/user_id/message_template/reply_target/enabled/secret_ciphertext）；`webhook_source_store` put/get/list/delete 按 id；secret 列是密文、明文不在表里；down 可回滚
- [ ] 4.2 实现(绿)：Alembic 迁移 + `platform/webhook_management/webhook_source_store.py`（手写 SQL、named params、`secret_crypto` 加解密）

## 5. managed admin REST API（CRUD）

- [ ] 5.1 写集成测试(红)：admin 鉴权下 create/list/delete webhook source；create 带 secret → 密文落库、响应不回显明文；非 admin 拒
- [ ] 5.2 实现(绿)：`platform/webhook_management/webhook_admin_api.py`（复用 connector_admin_api 鉴权模式）+ server.py 注册 router

## 6. managed 端点 + platform→node→agent 转发

- [ ] 6.1 写集成测试(红)：platform `POST /webhook/{id}`——未知 404、HMAC（用库内密文 secret）失败 403/成功 202、body/enabled 闸；成功 → 立即 202 且经转发通道把消息投目标 agent（mock `agent_transport`/forward，断言被调用且带 user_id/message/agent）；契约守护：webhook face 不破坏 agent⊥platform
- [ ] 6.2 实现(绿)：`platform/webhook_management` 挂公开 `POST /webhook/{source_id}` + server.py 注册；查库 source → 解密 secret 校验 → 构消息 → 202 + 后台经 `agent_transport`(DirectHttpAgentTransport→node `/forward/agents/{name}/chat`) 转发到目标 agent；不可达只记日志

## 7. 回投 reply_target（B）两态

- [ ] 7.1 写测试(红)：source 配 `reply_target`(内部 user_id) → run 结果投递（standalone 经 agent 连接器 `outbound`；managed 经 `outbound_connectors.notify_user`）；未配 → no-op；投递失败只记日志不影响 run
- [ ] 7.2 实现(绿)：reply_func 接线——按 `is_node_managed_runtime()` 选 directed-reach / 连接器；标记尽力而为

## 8. 闭环 + 守护 + 收尾

- [ ] 8.1 写守护/契约测试(红→绿)：模块边界——`runtime/agent_app` 的 webhook 路径不 import platform；webhook_router 中立两侧共用；standalone 在「无 platform、管理表不存在」下端点可用
- [ ] 8.2 跑 `make test-pr` + `make test-integration-ci`，对照 main 基线无新增失败；模块/层/plane 守护通过
- [ ] 8.3 openspec validate 通过；归档前确认所有 checkbox 为 [x]
