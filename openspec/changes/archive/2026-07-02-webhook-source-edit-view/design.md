## Context

托管 webhook 后端（`webhook_admin_api.py` + `webhook_source_store.py` + Alembic 113）与管理前端（`features/webhooks/`）均已上线，但前端只做了列表 + 新建 + 删除，且列表只展示 4 列。上一个 webhook-admin-ui 变更的 D2 明确记录：「要做安全的编辑需要新增一个保留原 secret 语义的 PATCH 接口，超出本次范围」——本次正是补这块。列表接口的 `_public_view` 其实已返回除密钥外的全部字段，因此「查看」缺的只是前端展示，「编辑」缺的是后端一个安全端点。

## Goals / Non-Goals

**Goals：**
- 管理员能在 SPA 里查看某条 webhook source 填写的全部字段（密钥除外，只显示「已设置/未设置」）。
- 管理员能安全编辑已有 source，且**不会因漏填密钥而清空已有密钥**。

**Non-Goals：**
- 不改 `webhook_sources` 表结构、不加迁移。
- 不加单独的 GET 单条详情接口（列表已返回足够数据）。
- 不做 webhook 调用历史/日志展示、不改入站校验逻辑。
- `id` 不可编辑（改 id = 换公开 URL，语义上应新建）。

## Decisions

**D1 · 单弹窗，只读默认态 + 「编辑」切换可改态。** 查看与编辑共用一套弹窗，打开先只读展示全部字段，右下角「编辑」按钮切到可改态并出现「保存/取消」。避免维护两套界面，保证展示与编辑字段一致。复用现有新建弹窗的控件（Select/Input/Switch）。

**D2 · 新增 `PUT /admin/webhooks/sources/{id}`，密钥用 `secret_action` 三态语义。** 请求体常规字段（`user_id` / `agent_id` / `message_template` / `reply_target` / `enabled`）整体替换；密钥经判别字段 `secret_action` 处理：
- `keep`（默认）→ 不碰 `secret_ciphertext`；
- `set` → 用请求体 `secret` 值 `encrypt_text` 覆盖（`set` 时 `secret` 必填，缺失 400）；
- `clear` → 置 NULL。

这是记忆里「掩码覆盖缺陷家族」的正解：不回显、不掩码、用显式动作区分「保持 / 更换 / 清除」，而非靠占位符猜测。

**D3 · store 新增 `update_source(...)` 做 `UPDATE`（非 upsert）。** 与 `put_source` 的 upsert 分开：`update_source` 目标行必须已存在（端点在调用前 `get_source` 判 404）。常规字段一条 `UPDATE` 全写；密钥按 `secret_action`——`keep` 不进 SET 子句、`set`/`clear` 才写 `secret_ciphertext`。这样 `keep` 路径物理上不可能触碰密钥列。同步刷新 `updated_at`。

**D4 · 不加 GET 单条接口，前端用列表行数据。** `_public_view` 已含 `message_template` / `reply_target` / `has_secret` 等全部非密钥字段，弹窗直接吃列表 query 缓存里的 `WebhookSourceRecord`。保存后 `invalidateQueries` 刷新列表即可（YAGNI）。

**D5 · `id` 只读；reply_target / agent 展示名称。** 编辑态 `id` 字段禁用。只读态里 `reply_target`（存的是 user_id）和 `agent_id` 用页面已有的 `users` / `agentNameById` 映射显示为人类可读名称，未命中则回落显示原值。

## Risks / Trade-offs

- **[secret_action 前端漏传]** → 后端 `secret_action` 默认 `keep`，即「不填就保持」，最安全的默认值；只有显式选「更换/清除」才动密钥。
- **[列表数据与真实值可能短暂不一致]** → 弹窗用列表缓存渲染，保存后 invalidate 刷新；因数据量小、单管理员操作，短暂陈旧可接受，不引入 GET 单条。
- **[`agent_id` 编辑为空]** → 沿用新建弹窗口径，前端强制必填（入站在 `agent_id` 为空时 409），避免编辑成打不通的 webhook。
