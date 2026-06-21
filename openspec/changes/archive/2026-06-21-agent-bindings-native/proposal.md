## Why

`agent-admin-ui` 的「Agent versions and bindings」要求**在 agent 详情里原生管理每类绑定**(skills/MCP/OAuth/KB/users)——旧 admin.html 满足它,但 C1 重写的 React SPA 的 agents 域**改成深链回 `/admin/ui-legacy`**(那个「Bindings and legacy entry points」aside),**不合规**。同时该要求还**没覆盖** IM 访问(群组 + DM/群开关)、默认 agent、secrets 这几类。本切片让 SPA 的 agent 详情**原生管理全部绑定**,并把缺的几类补进规格。

## What Changes

- 在 `features/agents/` 把深链 aside 换成**原生绑定面板**,均调既有 `/admin/agents/{name}/...` API:
  - **skills**:`GET /skills` + `PUT /skills/{name}` 启停;
  - **MCP**:`POST`/`DELETE /bindings/mcp/{id}`(选项来自 `GET /admin/mcp/servers`);
  - **OAuth**:`GET /bindings/oauth` + `POST`/`DELETE /bindings/oauth/{id}`(选项来自 `GET /admin/connectors`);
  - **KB**:`GET /kbs` + `POST`/`DELETE /kbs/{id}`;
  - **user 访问**:`GET /bindings` + `POST`/`DELETE /bindings/users/{id}`;
  - **IM 访问(新)**:`POST /bindings/groups` 群组白名单 + `PUT /im-capabilities` DM/群开关;
  - **默认 agent(新)**:`PUT /agents/{name}/default` / `DELETE /agents/default`;
  - **secrets(新)**:`GET /secrets` + `PUT`/`DELETE /secrets/{env}`(值只写不反显)。
- 绑定选择器复用已原生域(skills/kb/connectors/users)的 list API。已原生的列表/CRUD/版本激活不动。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `agent-admin-ui`: 扩充「Agent versions and bindings」——明确各绑定在 **React SPA** 原生管理(不再深链 legacy),并新增 **IM 访问(群组 + DM/群能力)**、**默认 agent**、**secrets** 三类绑定/设置。

## Impact

- **改动**:仅 `frontend/src/features/agents/`(`api.ts` + `page.tsx` + `page.test.tsx`)。
- **不碰** `routes.tsx`(agents 路由已在)→ **与正在跑的 W3/stats/nodes/tenancy 零文件重叠,可立即并行**;合并由主会话串行做。
- **后端**:不改(绑定 API 已完整)。
- **边界**:纯 `frontend/`;不碰 server.py / agent / schema。
- **解锁**:#1 落地后 agents 详情不再深链 legacy,为后续退役 `admin.html` 扫清最后一处 agent 深链。
