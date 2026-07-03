> TDD 硬门禁:每个实现 task 先写测试见红,再写实现见绿,不可跳步。后端最窄命令 `uv run pytest <file>::<test> -x -q`;前端最窄命令 `pnpm --dir frontend vitest run <file>`。测试任务已排在对应实现任务之前。

## 1. store:4 列往返(integration,TDD)

- [ ] 1.1 写测试 `tests/integration/test_mcp_server_store.py`(照该文件既有 auth_config 往返测试风格,`tmp_path` + Alembic 起真实管理库):`add_mcp_server(..., degrade_mode="strict", file_root="/x", file_isolation="off", approval_rules=[{"tool":"t","when":{"op":["send"]}}])` 后 `get_mcp_server` 读回这 4 个值(`approval_rules` 是 list-of-dict,不是 JSON 字符串);`edit_mcp_server` 单独更新 `degrade_mode` / `approval_rules` 生效;不传时 `_decode` 给默认值(degrade/""/on/[])。先见红。
- [ ] 1.2 实现:`mcp_server_store.py` 的 `add_mcp_server` 加 4 个 kwarg + INSERT 列/值;`_EDITABLE` 加 4 项;`approval_rules` 走 `json.dumps`/`json.loads`(进 `_decode` 的 JSON 分支 + `edit_mcp_server` 的 JSON 分支);前三者普通列;`_COLS` 追加 4 列;`_decode` 对缺列补默认;`_as_server_config` 带上 4 字段。跑 1.1 见绿。

## 2. Alembic 迁移:mcp_servers 加 4 列(integration,TDD)

- [ ] 2.1 写测试 `tests/integration/`(照既有"迁移后表有某列"风格,或直接在 1.1 的真实库上断言列存在):升级到 head 后 `mcp_servers` 有 `degrade_mode`/`file_root`/`file_isolation`/`approval_rules` 4 列且默认值正确;downgrade 后 4 列消失。先见红(列不存在)。
- [ ] 2.2 新建迁移 `migrations/versions/118_mcp_xfleetent_fields.py`:`revision = "118"`、`down_revision = "117"`(本分支基于 origin/main 建,已确认 main head=117 即 skill-gitops 的 `117_add_skill_git_source_skills_subdir`)。照 `109_mcp_auth_config.py`:`_has_table("mcp_servers")` guard + 4 个 `op.add_column`(`degrade_mode` server_default `'degrade'`、`file_root` `''`、`file_isolation` `'on'`、`approval_rules` sa.JSON/Text server_default `'[]'`);downgrade 用 `batch_alter_table` drop 这 4 列。跑 2.1 见绿。

## 3. admin API:body 收字段 + 校验 + GET 返回(integration,TDD)

- [ ] 3.1 写测试 `tests/integration/test_connector_admin_api.py`(复用现有 `/admin/mcp/servers` fixture):
  - `POST /admin/mcp/servers` 带 4 个 x-fleetent 字段(含 `approval_rules` 一条 `when` 规则)→ 201/200,`GET /admin/mcp/servers` 该 server 回显这 4 字段
  - `PUT` 单独改 `degrade_mode`/`approval_rules` 生效
  - 非法 `degrade_mode`(不在枚举)与坏 `approval_rules`(缺 `tool` / `when` 非字典)→ 422
  先见红。
- [ ] 3.2 实现:`McpServerCreateBody`/`McpServerEditBody` 加 4 字段(design D2 的默认与可选形态)+ `model_validator` 用 `McpApprovalRule` 逐条校验、枚举字段单独校验;`create_mcp_server`/`edit_mcp_server` 把字段透传给 store;`GET /mcp/servers` 的 `_from_row` 带上这 4 字段。跑 3.1 见绿。

## 4. materialize:store 行 → x-fleetent 块(integration,TDD)

- [ ] 4.1 写测试 `tests/integration/`(照既有 materialize/desired_state 测试,或 `test_materialize_mcp_map.py` 的物化断言风格,但需真实 store 行故放 integration):一个配了非默认 `degrade_mode`/`file_isolation`/`file_root`/`approval_rules` 的 store 行,经 `_mcp_servers_for_agent` + 物化后,`agent.yaml` 的 `mcpServers.<id>.x-fleetent` 下出现这 4 个字段(`approval_rules` 保留 `when`);全默认行则 `x-fleetent` 不出现这些键。先见红。
- [ ] 4.2 实现:`_mcp_servers_for_agent()` 构造 `McpServerSettings` 时补 4 个字段(`approval_rules` 转 `[McpApprovalRule(**r) for r in ...]`)。`_mcp_payload_to_map` 不改。跑 4.1 见绿。

## 5. 前端:logic 往返(TDD)

- [ ] 5.1 写测试 `server-dialog-logic.test.ts`(照既有 auth 往返测试):`ServerFormFields` 加 4 字段后,`serverFormFromEditing` 从记录回显(`approval_rules` 的 `when:null` → `conditions:[]`;`when` 字典 → conditions 数组);`buildServerPayload` 反向(空 conditions → `when:null`;丢弃空 arg/空 values 的条件);`canSubmitServer` 对空 tool 名的规则返回 false。先见红。
- [ ] 5.2 实现:`server-dialog-logic.ts` 扩 `ServerFormFields` + derive/build/validate;`connectors/api.ts` 给 `McpServerRecord`/`McpServerInput` 加 4 字段 + `McpApprovalRule` 类型。跑 5.1 见绿。

## 6. 前端:表单渲染(TDD)

- [ ] 6.1 写测试 `page.test.tsx`(MSW 复用现有 mock):打开新建表单,「fleetent 扩展」区展开后有 `degrade_mode`/`file_isolation` 下拉、`file_root` 输入、`approval_rules` 的「添加规则」;加一条规则 + 一个条件后提交,`POST` body 带正确的 `approval_rules` 结构;编辑一个带 `x-fleetent` 字段的 server 时正确回显;4 字段下方 `FieldPathHint` 显示 `mcpServers.<id>.x-fleetent.<字段>`。先见红。
- [ ] 6.2 实现:`server-dialog.tsx` 加可折叠「fleetent 扩展」小节 + 4 控件(含 approval_rules 三层嵌套增删 UI)+ `FieldPathHint`;`i18n/messages.ts` 补 en+zh 文案(降级策略/文件隔离/文件根目录/审批规则/工具名/条件/参数名/允许值 等)。跑 6.1 见绿。

## 7. Change 收尾验证

- [ ] 7.1 `make test-pr` + `make test-integration-ci` 全绿(无新增失败);其中 `test_module_dependency_guardrails` 不得因 `connector_admin_api` 新 import 报新跨面依赖。
- [ ] 7.2 `make test-frontend` 全绿(vitest + 覆盖率阈值 + tsc --noEmit + lint)。
- [ ] 7.3 手动核对:本地起 platform + vite dev server,Playwright 登录走完新建流程——填 4 个 x-fleetent 字段(含一条带 `when` 的 approval 规则)保存,确认落库;物化/查看该 agent 的 `agent.yaml` 确认 `x-fleetent` 块正确;编辑回显正确。
- [ ] 7.4 更新 `docs/capabilities/mcp.md`(若该文档描述了 admin 表单可配字段范围)与 `agent.yaml.example`(如需)——非代码产物,人工确认后再 commit。
