## 1. 前端测试先行（红）

- [ ] 1.1 在 `frontend/src/features/kb/page.test.tsx` 删掉已退役功能的用例(connector 注册/编辑/check/sync、文档导入 ingest、目录 sync),改/加用例断言:KB 页**不渲染** Connectors tab、不渲染导入/同步控件;保留 KB 列表/创建、文档 list/delete、绑定用例。跑 `yarn --cwd frontend vitest run features/kb` → 见红(因源码仍有死 UI / 旧用例引用将删的 export)

## 2. 删死 UI 与 hooks（绿）

- [ ] 2.1 `frontend/src/features/kb/api.ts`:删 `KbConnector` / `CreateConnectorInput` / `UpdateConnectorInput` / `kbConnectorsKey` / `useKbConnectorsQuery` / `useCreate|Update|Delete|Check|Sync|StatusConnectorMutation`;删文档导入 `useIngestMutation`(`POST /{kb_id}/documents`)与目录同步 `useSyncDocumentsMutation`(`POST /{kb_id}/sync`);保留 KB CRUD、`GET /{kb_id}/documents`、`DELETE …/documents/{doc}`、绑定、search/evaluation/observation
- [ ] 2.2 `frontend/src/features/kb/page.tsx`:删 Connectors `<TabsTrigger>`+`<TabsContent>`、`ConnectorDialog`、`ConnectorRow`、`CONNECTOR_KINDS`、ingest 对话框、`SyncDialog` 及其触发按钮和相关 import/state;若删后只剩单 tab,移除 `<Tabs>` 壳直接渲染 KB 列表
- [ ] 2.3 跑 `yarn --cwd frontend vitest run features/kb` → 见绿

## 3. 清死 i18n

- [ ] 3.1 `frontend/src/i18n/messages.ts`:删 KB 死键 `kb.tabConnectors` / `kb.addConnector` / `kb.connector*` / 文档导入与同步相关键;删旧 vault 页遗留的 `connectors.*`(subtitle / tabGrantsMatrix / addConnector / addTitle 等,页早已删)。两处 locale(en/zh 等)对称删
- [ ] 3.2 grep 确认无源码再引用被删键(`grep -rn "tabConnectors\|connectors\." frontend/src` 仅剩注释/无)

## 4. Spec 同步与质量门

- [ ] 4.1 `openspec validate align-kb-frontend-to-retired-ingest --strict` 通过
- [ ] 4.2 `make test-frontend`(vitest + tsc + eslint)全绿
- [ ] 4.3 `make frontend-build` 通过(新 dist 生成)
