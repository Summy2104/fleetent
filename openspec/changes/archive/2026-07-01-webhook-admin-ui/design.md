## Context

后端 webhook 托管能力（`webhook_admin_api.py` + `webhook_source_store.py` + `113_webhook_sources` 迁移）已上线，但只暴露 REST API，没有管理界面。现有前端已有成熟的"表格 + 新建弹窗 + 删除确认"CRUD 范式（`features/mcp/page.tsx`），本次照此范式落地。

## Goals / Non-Goals

**Goals:** 管理员能在 SPA 里自助新建/查看/删除托管 webhook source，不用手调 REST API；创建后能直接拿到可用的完整 URL。
**Non-Goals:** 不做"编辑"（受限于后端 upsert 语义会清空未传的 secret，见 D2）；不改后端；不做 webhook 调用历史/日志展示。

## Decisions

**D1 · 照 mcp 页面范式，单表 + 新建弹窗 + 删除确认。** 不做子区拆分（webhook source 字段远比 MCP server 简单，单一表格即可）。

**D2 · 不支持编辑，范围收敛为新建 + 删除。** 后端 `put_source()` 是"给什么存什么"的 upsert：如果编辑时不重新填 secret，会把已有密钥覆盖成 NULL。要做安全的编辑需要新增一个保留原 secret 语义的 PATCH 接口，超出本次范围；改配置 = 删除重建。

**D3 · `agent_id` 前端强制必填。** 后端 Pydantic 模型允许 `agent_id: int | None = None`，但入站 `POST /webhook/{id}` 在 `agent_id is None` 时直接 409。前端把它当必填字段（下拉选 agent），避免管理员建出永远打不通的 webhook。

**D4 · secret 随机生成 + webhook URL 展示。** 用 `crypto.getRandomValues` 生成 32 字节 hex 作为默认 secret 建议值（管理员可改）；创建成功后用 `window.location.origin` 拼出完整 webhook URL 供复制粘贴到外部系统，附一行"反向代理/独立域名请自行替换"的提示——后端没有存"平台对外域名"这个配置项，只能靠浏览器当前 origin 近似。

## Risks / Trade-offs

- **[无编辑能力]** → 已与用户确认接受，小范围配置改动用删除重建代替；后续如需编辑再补 PATCH 接口。
- **[URL 拼接不一定准]** → 反向代理/独立域名场景需管理员手动替换域名部分，已在 UI 里提示。
- **[`agent_id` 前端强制 vs 后端仍允许 null]** → 属于前端侧防呆，不代表后端契约收紧；后端保持原样。
