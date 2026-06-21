## Context

平台管理前端现状是单个 4731 行手写 `static/admin.html`(无框架/无构建/无测试,343 个内联函数),无法并行开发、编辑易错、零测试守护,且多处管理能力缺 UI。已决定**完全重构为 React+TS+Vite 的 SPA**,但采用**增量迁移**:本切片(C1)只立地基 + 测试栈 + TDD 门禁 + 第一个域(agents)达 legacy parity,其余域留作后续可并行 change。

约束(已确认):on-prem / 数据主权 / 无 CDN → **运行时无 Node**,只能构建期产出静态资源由 FastAPI 托管;后端已有干净的 admin REST API,前端为纯客户端 SPA;TS 可接受;包管理用 yarn;前端必须有测试栈并按 TDD 开发。

## Goals / Non-Goals

**Goals:**
- 立起 `frontend/`(Vite+React18+TS)工程与构建管线,产物为静态 `dist/` 由 FastAPI 在 `/admin/ui` 托管(SPA fallback)。
- 一等的前端测试栈(Vitest+RTL+jsdom+MSW+Playwright)与门禁接线(`make test-frontend` 进 PR gate + 覆盖率阈值),使后续各域可按 TDD 开发。
- 认证 / api client / TanStack Query 服务端状态层 / 路由 / 应用壳。
- agents 域以 TDD 实现并与旧版 parity,作为后续各域照抄的范式。
- 新旧共存:legacy 移到 `/admin/ui-legacy` 持续可用;新 SPA 中未迁移的域导航直接深链到 legacy,运维全程不丢功能。

**Non-Goals:**
- 不迁移 skills/kb/providers/connectors/mcp/nodes/tenancy/users/sessions 等域(留作 C2..Cn,可并行)。
- 不删除 `admin.html`(留到最后一个域迁完的 change)。
- 不引入 SSR / 运行时 Node;不碰 agent 运行时;不新增/改管理表;不破坏 agent↔platform 解耦。
- 不在本切片重做后端 API(至多补 1-2 个 agents parity 必需的小端点)。

## Decisions

**D1 · 纯客户端 SPA,排除 SSR。** 后端是 FastAPI(Python),SSR(Next/Nuxt)需运行时 Node,违背 on-prem 极简交付。故 React+TS+Vite 构建为静态 bundle,FastAPI 托管。备选 SSR—否决。

**D2 · 托管与构建。** `frontend/` 为仓库根独立工程(自带 package.json/tsconfig/vite.config),`yarn build` → `frontend/dist`(gitignore,CI/打包期构建);FastAPI 在 `/admin/ui` 挂载该目录并对未知子路径回落 `index.html`(SPA fallback),且 fallback **不得遮蔽** `/admin/*` API 与 `/admin/ui-legacy`。运行时交付物 = 静态文件 + Python,无 Node。

**D3 · 新旧共存与切换。** 旧 `admin.html` 迁到 `/admin/ui-legacy` 全功能保留;`/admin/ui` 服务新 SPA;新 SPA 导航中**尚未迁移的域**直接深链到 `/admin/ui-legacy` 对应位置——运维任何阶段都有完整功能。最后一个域迁完的 change 才删 legacy。

**D4 · 应用栈。** 服务端状态用 **TanStack Query**(CRUD 缓存 + mutation 后失效列表 + 401→重登,管理台量身定做);路由 React Router;组件/样式 **shadcn/ui + Tailwind**(copy-in、无运行时外链,贴合 on-prem 自包含);认证为 admin Session token context,统一注入请求头。备选 Mantine(电池更全)—design review 可换,不影响地基结构。

**D5 · 测试栈与 TDD 是地基的一部分,先于功能代码。** Vitest + @testing-library/react + jsdom(组件/hook)、MSW(拦 HTTP 测 query/mutation/401,不散 mock)、Playwright(登录→agents 真实托管烟测)。新增 `make test-frontend` = `vitest run`(+覆盖率阈值)+ `tsc --noEmit` + lint,**接进 PR 门禁**并在 CI 硬卡。前端按 TDD 硬门禁:测试任务先于实现任务,最窄命令 `yarn --cwd frontend vitest run <file>` 见红→实现→见绿。

**D6 · 增量迁移,拒绝 big-bang。** 343 函数一次性重写=长期无可交付+高风险。C1 只交付地基 + agents 域 parity;其余域 = 后续 change,地基落地后**彼此并行**(每个域一个 `features/<domain>/` 文件夹 + 路由)。

## Risks / Trade-offs

- **[首引 Node/yarn 工具链]** → 仅构建期/CI;运行时与交付物仍纯静态+Python。在 CI 固定 Node 版本 + 锁文件(`yarn.lock`)保证可复现。
- **[SPA fallback 遮蔽 API/legacy 路由]** → fallback 仅对非 `/admin/(api 前缀)`、非 `/admin/ui-legacy` 的未知路径返回 index.html;加 Python 集成测试断言 API 与 legacy 仍可达。
- **[前端覆盖率阈值流于形式]** → 设一个有意义的初始阈值(对标 Python unit gate 口径),只测真实组件/hook 行为,不靠快照凑数。
- **[agents parity 漏项]** → 以 legacy agents tab 的能力清单为 parity 验收基准(列表/建/改/删/启停/归档/恢复/克隆/版本激活/各类绑定入口),逐条对照。
- **[mid-migration 操作体验割裂]** → D3 的「未迁移域深链 legacy」保证全程功能完整。

## Migration Plan

- 部署:CI 跑 `yarn --cwd frontend install --frozen-lockfile && yarn --cwd frontend build` 产出 `dist/` 随包发出;运行时 FastAPI 直接托管。回滚:`/admin/ui` 可临时切回 legacy(legacy 始终在 `/admin/ui-legacy`)。
- 渐进:C1 落地后,C2..Cn 逐域把导航深链从 legacy 换成原生 SPA 页;全部域迁完的 change 删 `admin.html` 与 `/admin/ui-legacy` 路由。
- 数据:无 schema/迁移改动。
