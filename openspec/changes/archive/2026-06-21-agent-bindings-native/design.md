## Context

C1 的 agents 域已原生:列表/建/改/启停/归档/克隆/删 + 版本列表与激活。但 `features/agents/page.tsx` 的绑定区是「Bindings and legacy entry points」aside,各类绑定深链 `/admin/ui-legacy#...` —— 与 `agent-admin-ui` 既有「Agent versions and bindings」要求(原生管理每类绑定)不符。绑定 API(`agent_admin_api`)齐全;skills/kb/connectors/users 域已原生(可做选择器数据源)。

## Goals / Non-Goals

**Goals:** agent 详情原生管理全部绑定(skills/MCP/OAuth/KB/users)+ 补 IM 访问 / 默认 agent / secrets;与 legacy 绑定区 parity;TDD + MSW。
**Non-Goals:** 不改后端绑定 API;不重做已原生的列表/CRUD/版本;不引入新依赖;不碰其它域。

## Decisions

**D1 · 一个原子 change,不拆。** 所有绑定都改 `features/agents/page.tsx` + `api.ts`;拆成多个会在同一文件互撞(比 routes.tsx 更糟)。故单 change、一个 apply 会话(偏大但内聚),内部分模块 TDD。

**D2 · 选择器复用原生域 list。** MCP 选项 `GET /admin/mcp/servers`、OAuth `GET /admin/connectors`、KB/skills/users 用各自 list API;当前绑定态用 agent 的绑定 GET。

**D3 · secrets 值只写不反显。** `GET /secrets` 只回 env 名/状态;`PUT /secrets/{env}` 写值不回显;删除/解绑给确认。

**D4 · 不碰 routes.tsx → 可立即并行。** agents 路由已注册,绑定是详情页内面板、非新路由。本 change 只动 `features/agents/`,与在跑的 W3/stats/nodes/tenancy 零重叠;合并由主会话串行做(届时 main 的 agents 文件未被它们动过,合并干净)。

**D5 · 合规 + 扩充。** skills/MCP/OAuth/KB/users 是让 SPA 追上既有规格(legacy 已满足);IM 访问/默认/secrets 是规格新增。

## Risks / Trade-offs

- **[域大、测试面广]** → 每类绑定一组 api+page 测试,分模块 TDD;page.test 用 `within(<binding section>)` scope 避免同名二义(沿用之前教训)。
- **[secrets/凭证泄露]** → 只写不反显,测试守。
- **[parity 漏项]** → 以 legacy agents drawer 绑定区逐类对照(skills/MCP/OAuth/KB/users/IM/默认/secrets)。
- **[与并行项的合并]** → 不碰 routes.tsx、只动 features/agents/,合并冲突面极小;仍由主会话串行合。
