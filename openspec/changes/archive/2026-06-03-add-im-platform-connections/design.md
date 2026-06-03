## Context

后端已存在完整 IM 连接器栈，本变更基于其增量构建，不重造：
- `im_connectors` 表（`platform` UNIQUE、`enabled`、`allowlist_enforced`、`config` JSON、`status`、心跳/错误、时间戳）— `im_connector_store.py`。
- 凭证解析：`im_connector_config.py`，`resolve()`（DB config 优先，`.env` fallback）、`resolve_masked()`（末 4 位掩码）、`set_config()`（→ `upsert_connector`）、`PLATFORM_CONFIG_KEYS`。
- HTTP：`im_admin_api.py`（prefix `/admin/im`）已有 `GET /connectors`、`GET /connectors/{platform}`、`PATCH /connectors/{platform}`（写 config）、`POST .../enable|disable`，均 admin-only、读取掩码。
- 适配器启停：`im_connector_manager.py`。
- 前端：`static/admin.html` 自包含 vanilla-JS SPA，调 `/admin/*` JSON API；当前**无**任何 IM 连接器界面。

缺口：凭证字段 schema 不全；无「新建连接」HTTP 入口（`PATCH` 对未存在平台 404）；前端无录入界面。

## Goals / Non-Goals

**Goals:**
- 复用 `im_connectors` + `im_connector_config`，补全 telegram/slack/whatsapp 的凭证字段。
- 加 `POST /admin/im/connectors` 让后台可为新平台创建连接（幂等 upsert）。
- admin.html 加连接器区 + 「Add connection」弹窗：platform 下拉 + 按平台动态字段 + 掩码回显 + 启用/停用。

**Non-Goals:**
- 不新增数据库表，不新增 Alembic migration（`config` 已是 JSON 列）。
- 不做凭证 at-rest 加密（需先定 on-prem 密钥管理）；当前靠 admin-only + 掩码读 + gitignored 库文件。
- 不改 OAuth `connector_management` 域（那是另一套，针对 OAuth/MCP）。
- 不实现 WhatsApp 适配器运行时（仅凭证录入；未配置/无适配器平台保持 `unconfigured`，不启动）。

## Decisions

**D1: 复用 `im_connectors`，不建 `platform_connections` 新表。**
早期设想新表 + JSON metadata 列 + Alembic migration，是在未发现既有连接器栈前定的。既有表语义完全一致（平台级配置、JSON config、status）。新建表将重复基础设施并违反 CLAUDE.md「禁止扩散 SQLite 细节 / 统一 store 边界」。→ 选复用。代价：沿用既有 `_init_db()` 建表（legacy 模式），但本变更不新增 store，仅扩 Python dict + 加一个端点，无 schema 变更。

**D2: 凭证字段集中在 `PLATFORM_CONFIG_KEYS`（单一事实源）。**
后端解析、掩码、前端动态表单都从同一份字段定义派生。前端通过既有 `GET /connectors`（或新增一个 schema 端点）拿字段；为零额外端点，前端内联同一份字段表，并由后端 spec 测试守住一致性。备选：新增 `GET /connectors/schema` 端点回传字段——更 DRY 但多一个面。**决定**：前端内联字段表，后端 `PLATFORM_CONFIG_KEYS` 为权威；用测试断言两边平台字段一致，避免漂移。

**D3: 新建走 `POST /admin/im/connectors`，幂等。**
body：`{platform: str, config: dict[str,str]}`。实现调 `im_connector_config.set_config(platform, config)`（内部 `upsert_connector`，靠 `platform` UNIQUE 幂等）。校验 platform ∈ {telegram, slack, whatsapp}，admin-only。`PATCH` 保留给已存在平台改 config/allowlist。

**D4: Slack/WhatsApp 字段扩充 + `.env` 映射。**
`PLATFORM_CONFIG_KEYS`：slack 增 `signing_secret`；whatsapp 设 `phone_number_id`/`access_token`/`verify_token`/`business_account_id`。`_ENV_MAP` 同步加可回退键（whatsapp 各键、slack signing_secret），未配 `.env` 字段则 fallback 跳过。

**D5: 前端动态表单。**
弹窗 platform `<select>` change → 按内联字段表重渲染 `<input>`（敏感字段 `type=password` / `autocomplete=off`）。列表回显走 `resolve_masked`。启用/停用调既有 enable/disable。viewer 隐藏管理控件（沿用既有 role-gate 模式）。

## Risks / Trade-offs

- [前后端字段表漂移] → 后端 `PLATFORM_CONFIG_KEYS` 为权威，加测试断言前端 admin.html 含每平台字段名；schema 改动必同步两处。
- [明文凭证 at-rest] → 本次不解决；admin-only + 掩码读 + 库 gitignored，加密单列后续变更并在 proposal 注明。
- [掩码后无法回填编辑] → 编辑时不预填密文（显示掩码占位），管理员重填完整凭证才提交；避免把掩码串误存为真值。
- [WhatsApp 无适配器] → 仅存凭证；manager 对无适配器/无凭证平台置 `unconfigured` 不启动（既有行为），不报错。
- [legacy `_init_db` 建表] → 不在本变更范围内改造为 Alembic；仅复用，不新增 store，符合「不新增 store 复制 `_init_db`」约束。

## Migration Plan

1. 扩 `PLATFORM_CONFIG_KEYS` + `_ENV_MAP`（纯数据，无 schema 变更）。
2. 加 `POST /admin/im/connectors`。
3. admin.html 加连接器区 + 弹窗。
无 DB migration、无回滚脚本；回滚 = 还原代码。既有已 seed 连接器不受影响（新字段缺失即视为未配，照常掩码/fallback）。

## Open Questions

- 凭证 at-rest 加密的密钥管理方案（后续变更）。
