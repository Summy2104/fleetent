## Why

`kb-retire-platform-ingest` 退役了平台侧 KB ingest 控制面(删 `/admin/kb/connectors/*`、`POST /{kb_id}/documents`(import)、`/{kb_id}/sync`)。但 **React admin SPA 的 KB 页没跟上**——仍渲染 Connectors tab、文档导入、目录同步 UI,调的是**已删的后端端点**(点了就 404)。这是 retire 那刀的**前端对应物**:前后端对齐。

(另:旧的 tool-OAuth-vault "Connector" 主菜单页源码早删了[`cb95c2d2`],只是 `frontend/dist` 旧 build 还显示——已 `make frontend-build` 重建修复,不在本 change;本 change 只处理**当前源码里仍存在**的死 KB UI。)

## What Changes

- **删 KB 页 Connectors tab + 整套连接器管理**:ConnectorDialog / ConnectorRow / `useKbConnectorsQuery` / `useCreate|Update|Delete|Check|Sync|StatusConnectorMutation` / `CreateConnectorInput` / `KbConnector` / `UpdateConnectorInput` / `CONNECTOR_KINDS` / `kbConnectorsKey`(调 `/admin/kb/connectors/*`,已退役)。
- **删文档导入 UI**:ingest 对话框 + `useIngestMutation`(`POST /{kb_id}/documents`,已退役)。标准 KB 模型下文档摄取归 KB 服务(connector 自动同步),平台 admin 不再导入。
- **删目录同步 UI**:`SyncDialog` + `useSyncDocumentsMutation`(`POST /{kb_id}/sync`,已退役)。
- **清死 i18n**:`kb.tabConnectors` / `kb.addConnector` / `kb.connector*` / 导入/同步相关键;以及旧 vault 页遗留的 `connectors.*`(subtitle/tabGrantsMatrix/addConnector 等,页已删)。
- **更新对应前端测试**(`features/kb/page.test.tsx` 里 connector/import/sync 用例)。

不改变:KB 页保留的活功能——KB 定义 list/create/edit/archive、文档 **list / preview chunks / delete**、agent 绑定、检索 playground / evaluations / observation;后端(已退役,不碰);MCP Servers 菜单(活的,不碰)。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `kb-admin-ui`: SPA 的 KB 管理范围去掉 ingest documents / trigger sync / manage KB connectors(对应后端已退役);保留 KB 定义 CRUD、文档 list/delete、agent 绑定。

## Impact

- **owning area**:`frontend/src/features/kb/`(page.tsx / api.ts / page.test.tsx)+ `frontend/src/i18n/messages.ts`(死键)+ `kb-admin-ui` spec。**不碰后端、不碰 src/fleetent**。
- **public API surface**:无后端变更;前端移除对已删端点的调用。
- **owned tables**:无。
- **cross-module 依赖**:无。
- **行为**:KB 页不再显示连接器/导入/同步(它们点了本就 404);其余 KB 管理不变。
- **测试**:`make test-frontend`(vitest + tsc + eslint)绿;`make frontend-build` 通过。
