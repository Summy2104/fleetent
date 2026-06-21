## Context

C1(已在 main)的 `features/agents/` 是已坐实的港域范式;域在 `app/routes.tsx` 三处登记,未迁域走 `legacyLinks`(Connectors 现为其中一条,锚点 `#oauth`)。legacy 的 Connectors tab 同时含 OAuth 外部服务与 MCP servers,两者都 create-only。本切片照范式港 Connectors,补齐 edit/delete/test。

## Goals / Non-Goals

**Goals:** Connectors 域原生进 SPA,OAuth 外部服务与 MCP servers 都做到完整 CRUD + 测试 + 各自的运维动作;闭合 create-only;TDD + MSW。
**Non-Goals:** 不改后端 OAuth/MCP API(已完整);不动其它域;不在前端持有/反显任何密钥;不引入新依赖。

## Decisions

**D1 · 照 agents 范式,两子区组织。** `features/connectors/api.ts` 暴露 OAuth hooks(list/create/update/delete/test/lifecycle/grants/revoke/offboarding/credentials)与 MCP hooks(list/create/update/delete/test/reconnect/tools/doctor),mutation 后失效相关列表。`page.tsx` 两子区(OAuth 外部服务 + MCP servers),各自列表 + 建/改双模 + 删确认 + 测试。

**D2 · 闭合 create-only。** OAuth 连接器与 MCP server 均必须含 edit(PUT)、delete(DELETE+确认)、test(POST)——这是配错能改/能删/能验的关键。

**D3 · OAuth 授权/回调与凭证。** 授权是浏览器跳转(`/connectors/authorize/{service}` → `/callback`),沿用既有后端端点;写凭证经 `POST /connectors/{service}/credentials`,前端只写不反显;测试断言不渲染明文凭证。

**D4 · routes.tsx 唯一共享缝。** 注册 connectors(锚点对齐 legacy `#oauth` 语义)+ 从 `legacyLinks` 删 Connectors。与同批 kb/skills 仅此文件相撞。

## Risks / Trade-offs

- **[与同批域撞 routes.tsx]** → 保留各域条目 + 各自删自己 legacy link。
- **[凭证泄露]** → 前端只写不反显;测试守这条。
- **[域偏大(两子区 × 完整 CRUD)]** → OAuth/MCP 两子区分别 TDD;parity 以 legacy #oauth tab 两块能力逐条对照。
- **[OAuth 跳转流测试]** → 授权/回调以跳转 + 后端处理为主,前端测可聚焦"发起授权链接正确""回调后状态刷新",真实 OAuth 往返由后端既有逻辑负责。
