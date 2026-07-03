## Why

`agent.yaml` 里每个 MCP server 的 `x-fleetent` 扩展块承载 4 个 fleetent 专属字段:`degrade_mode`(不可用时的降级策略)、`file_root` / `file_isolation`(沙箱 `/exchange` 文件桥接)、`approval_rules`(哪些工具调用要走人工审批)。这 4 个字段在**托管路径里彻底断链**:前端 MCP server 表单没有对应输入框,平台管理库 `mcp_servers` 表也没有对应列,materialize 物化时只能取默认值。管理员想配它们只能手改 `agent.yaml`——而托管 agent 的 `agent.yaml` 是从平台 DB 物化出来的,手改会在下次 reconcile 被覆盖,等于没有可用入口。

上一轮 `2026-07-01-mcp-admin-yaml-path-hints` 已把这 4 个字段的 `agent.yaml` 路径提示接上(`mcp_yaml_field_paths()` 会算出 `mcpServers.{id}.x-fleetent.degrade_mode` 等),但表单不渲染这些字段的输入框——本次补上真正的查看/编辑能力,闭合"提示已在、输入框缺失"的缺口。

## What Changes

- **后端 store**:`mcp_server_store.mcp_servers` 表新增 4 列 `degrade_mode` / `file_root` / `file_isolation` / `approval_rules`(前三者 TEXT,`approval_rules` 存 JSON,与 `args`/`env`/`auth_config` 同款序列化)。`add_mcp_server` / `edit_mcp_server` / `_decode` / `_EDITABLE` / `_COLS` 补齐;沿用既有 `_select_rows` 对旧库"无此列"的兜底 fallback。
- **Alembic 迁移**:管理库 `mcp_servers` 加这 4 列(带 `server_default`,`approval_rules` 默认 `[]` 的 JSON)。管理表按规矩走 Alembic,不在 store `_init_db()` 建。
- **后端 admin API**(`connector_admin_api.py`):`McpServerCreateBody` / `McpServerEditBody` 新增这 4 字段;用 `config.py` 现成的 `McpServerSettings` / `McpApprovalRule` 校验(枚举合法性 + `approval_rules` 结构),非法值拒绝。`GET /admin/mcp/servers` 响应带上这 4 字段。`create_mcp_server` / `edit_mcp_server` 把字段透传给 store。
- **后端 materialize**(`_mcp_servers_for_agent`):把 store 行的这 4 个值传进 `McpServerSettings`。传进去后既有的 `_mcp_payload_to_map` 会自动把非默认值提到 `x-fleetent` 下——**物化整形逻辑零改动**。
- **前端**:`server-dialog.tsx` 在鉴权区与 args/env 之间加一个「fleetent 扩展」小节(建议可折叠),4 个控件:`degrade_mode` / `file_isolation` 下拉、`file_root` 单行输入、`approval_rules` 三层嵌套编辑器(规则 → 工具名 + 条件列表 → 参数名 + 允许值列表)。`server-dialog-logic.ts` 补 derive/build/validate;`connectors/api.ts` 扩类型;补 i18n。4 字段一直显示、不按 transport 隐藏。
- **field-schema 端点零改动**:`mcp_yaml_field_paths()` 已能算出这 4 条路径,前端直接复用现有 `FieldPathHint`。

## Capabilities

### New Capabilities

(无)

### Modified Capabilities

- `mcp-server-admin`:新增"MCP server 表单可查看/编辑全部 4 个 `x-fleetent` 字段(degrade_mode / file_isolation / file_root / approval_rules)"——此前表单只暴露标准字段 + 鉴权,这 4 个 fleetent 扩展字段无输入框、无落库、无物化。

## Impact

- **owning package**:`platform/connector_management`(admin API + store)、`platform/agent_lifecycle`(materialize)、`frontend/src/features/mcp` + `features/connectors`。`config.py` 的 `McpServerSettings` / `McpApprovalRule` 已存在,不改归属。
- **public API surface**:`POST/PUT /admin/mcp/servers` 请求体各加 4 个可选字段;`GET /admin/mcp/servers` 响应各加 4 个字段。不新增端点;`GET /admin/mcp/field-schema` 不变。
- **owned tables**:管理库 `mcp_servers` 加 4 列(Alembic 拥有)。
- **config namespace**:`mcpServers.<id>.x-fleetent.{degrade_mode,file_root,file_isolation,approval_rules}` —— 已由 `McpServerSettings` / `MCP_FLEETENT_EXT_DEFAULTS` 定义,**不新增 namespace**。
- **cross-module dependencies**:`connector_admin_api.py`(② 控制 face)import `config.py`(中立核心,与它已 import 的 `mcp_yaml_field_paths` 同源)做校验;MUST NOT import `materialize.py`(③ 编排 face)。无新增反向依赖,复用 `2026-07-01` 那次确立的面边界处理。
- **migration / shim plan**:新 Alembic 迁移 `revision = "118"`、`down_revision = "117"`(本分支基于 origin/main 建,已确认 main head=117)。store `_select_rows` 已有旧库 fallback 惯例,对新列同样兜底。
- **边界**:不改 `_mcp_payload_to_map` / `MCP_FLEETENT_EXT_DEFAULTS` 的整形行为;不改 `mcp_yaml_field_paths()`;不动审批门 `approval_policy.py` 的匹配逻辑(仅让配好的规则经既有物化链路落到 `agent.yaml`)。
