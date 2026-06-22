# admin-frontend-spa Specification

## Purpose
定义平台管理 SPA 的工程形态、静态构建与 FastAPI 托管约束、认证与数据层行为，以及各管理域迁移完成后的前端能力基线，确保 `/admin/ui` 成为唯一且可验证的管理入口。
## Requirements
### Requirement: SPA 工程与构建产物

平台管理控制台 SHALL 由仓库根 `frontend/` 下的 React + TypeScript + Vite 工程构建。构建 MUST 产出**纯静态资源**(`frontend/dist/`),运行时 MUST NOT 依赖 Node 进程。`dist/` MUST 被 gitignore 并在 CI/打包期由 `yarn build` 生成。包管理 MUST 用 yarn(锁文件入库)。

#### Scenario: 构建产出静态资源

- **WHEN** 在 `frontend/` 运行 `yarn install --frozen-lockfile && yarn build`
- **THEN** 生成 `frontend/dist/`,内含 `index.html` 与打包后的 JS/CSS 静态资源
- **AND** 资源不引用任何外部 CDN / 运行时外链

### Requirement: FastAPI 托管 SPA 且不遮蔽 API

平台 SHALL 在 `/admin/ui` 托管构建出的 SPA,并对 `/admin/ui` 下的未知子路径回落到 SPA 的 `index.html`(client-side 路由)。该 fallback MUST NOT 遮蔽 `/admin/*` 的 admin API 端点。

#### Scenario: 深链命中 SPA fallback

- **WHEN** 浏览器直接访问 `/admin/ui/agents` 这类 client-side 路由
- **THEN** 平台返回 SPA 的 `index.html`,由前端路由渲染对应页面

#### Scenario: API 不被 fallback 吞掉

- **WHEN** 请求命中某个 `/admin/<resource>` API 端点
- **THEN** 平台返回该 API 本身,而非 SPA 的 `index.html`

### Requirement: Deployed platform serves the built SPA from a resolvable dist

The platform SHALL resolve the admin SPA dist directory in a deployment-robust way: it SHALL honor a `FLEETENT_ADMIN_UI_DIST` environment variable when set, otherwise fall back to the repo-relative `frontend/dist`. When the dist exists, `/admin/ui` SHALL serve it; when it does not, the platform SHALL return a clear "frontend not built" error (503) rather than a blank page, so the failure is diagnosable.

#### Scenario: Serve dist from an overridden location

- **WHEN** `FLEETENT_ADMIN_UI_DIST` points at a directory containing a built SPA
- **THEN** `/admin/ui` serves that build, regardless of the process working directory

#### Scenario: Default resolution serves the built repo dist

- **WHEN** `FLEETENT_ADMIN_UI_DIST` is unset and `frontend/dist` has been built
- **THEN** `/admin/ui` serves the repo's built dist

#### Scenario: Unbuilt dist gives a clear error

- **WHEN** no built dist is found at the resolved location
- **THEN** `/admin/ui` returns a 503 with a clear "frontend not built" message (not a blank/200 page)

### Requirement: SPA 认证与会话流

新 SPA SHALL 通过现有 admin 登录端点获取 admin Session token,并在所有 admin API 请求中注入该凭证。会话失效(HTTP 401)时 SHALL 引导用户重新登录,MUST NOT 把用户卡在静默失败状态。

#### Scenario: 登录后访问受保护资源

- **WHEN** 用户用合法 admin 凭证登录
- **THEN** SPA 保存会话凭证并在后续 admin API 请求头中携带它,受保护页面正常加载

#### Scenario: 会话失效引导重登

- **WHEN** 某个 admin API 请求返回 401
- **THEN** SPA 清理会话并把用户引导回登录界面,而非停在空白/转圈

### Requirement: 服务端状态经统一数据层

新 SPA 对 admin REST API 的读写 SHALL 经统一的服务端状态层(TanStack Query):列表/详情为查询,创建/编辑/删除为 mutation,且 mutation 成功后 MUST 失效相关查询缓存以反映最新状态。

#### Scenario: 变更后列表自动刷新

- **WHEN** 用户在某域创建或删除一条记录且 mutation 成功
- **THEN** 相关列表查询被失效并重新拉取,UI 反映变更,无需手动刷新页面

### Requirement: agents 域达 legacy parity

新 SPA 的 agents 领域 SHALL 在功能上与旧 `admin.html` 的 Agents 标签页 parity:至少覆盖 agent 列表、创建、编辑(system_prompt / 工具 / 模型配置)、删除、启用/禁用、归档/恢复、克隆、版本查看与激活,以及 skills/KB/MCP/OAuth/users 绑定入口。

#### Scenario: agents 增删改查与旧版一致

- **WHEN** 运维在新 SPA 的 agents 页执行列表/创建/编辑/删除/启停/归档/恢复/克隆/激活版本
- **THEN** 每项行为调用对应 admin API 并产生与 legacy 一致的结果

### Requirement: 前端测试栈与 TDD 纪律

`frontend/` SHALL 自带测试栈:Vitest + @testing-library/react + jsdom 覆盖组件/hook,MSW 拦截 HTTP 以测试数据层(加载/缓存/mutation 失效/401),Playwright 跑端到端烟测。前端功能 SHALL 按 TDD 开发——测试先于实现。

#### Scenario: 数据层 hook 以 mock API 测试

- **WHEN** 运行某 query/mutation hook 的 Vitest 测试
- **THEN** 该测试经 MSW 提供 mock 响应,断言加载态、成功态、mutation 后失效与 401 处理,无需真实后端

#### Scenario: 登录到 agents 的端到端烟测

- **WHEN** Playwright 对真实托管的 SPA 跑烟测:登录 → 进入 agents 页
- **THEN** agents 列表成功渲染,证明「构建 → FastAPI 托管 → 认证 → 数据层 → 页面」整条链路连通

