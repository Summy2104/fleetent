> 前端按 TDD 硬门禁开发:每个功能任务先写测试见红 → 实现见绿。前端最窄命令 `yarn --cwd frontend vitest run <file>`;Python 侧托管接线用 `uv run pytest <file>::<test> -x -q`。测试任务排在实现任务之前,不可跳步。测试栈(组 2)必须先于任何 feature TDD(组 4/6)就位。

## 1. 工程脚手架与构建管线

- [x] 1.1 在仓库根建 `frontend/`:Vite + React 18 + TypeScript 工程(package.json/tsconfig/vite.config),yarn 锁文件;`.gitignore` 加 `frontend/node_modules`、`frontend/dist`。
- [x] 1.2 加 Tailwind + shadcn/ui 基础配置与一个最小 App 壳;`yarn --cwd frontend build` 能产出 `frontend/dist/index.html` + 资源。
- [x] 1.3 在 `Makefile` 加 `frontend-install`/`frontend-build` 目标(供 CI 与本地用)。

## 2. 测试栈与门禁(先于任何 feature 代码)

- [x] 2.1 配置 Vitest + @testing-library/react + jsdom + MSW;写一个最小冒烟组件测试,`yarn --cwd frontend vitest run` 见绿(证明 harness 可用)。
- [x] 2.2 配置 Playwright(对 `yarn preview`/托管的 dist 跑),先放一条占位 e2e(后续 7 填实)。
- [x] 2.3 加 `make test-frontend` = `vitest run`(带覆盖率阈值)+ `tsc --noEmit` + lint;设定初始前端覆盖率阈值。
- [x] 2.4 把 `make test-frontend` 接进 CI PR 门禁(Bitbucket Pipelines):安装锁文件依赖 → 跑 `make test-frontend`,任一失败则 build 失败。

## 3. FastAPI 托管接线与新旧共存(Python 侧)

- [x] 3.1 写集成测试(`tests/integration/`):断言 `/admin/ui` 返回 SPA `index.html`、`/admin/ui/<深链>` 回落 index.html、`/admin/ui-legacy` 仍返回旧 admin.html、且某个 `/admin/<resource>` API 不被 fallback 吞。先见红。
- [x] 3.2 实现 `server.py`/platform 托管:`/admin/ui` 挂载 `frontend/dist` + SPA fallback(不遮蔽 API 与 legacy),旧 admin.html 迁 `/admin/ui-legacy`。跑 3.1 见绿。

## 4. 认证 + api client + TanStack Query 数据层(TDD)

- [x] 4.1 写测试(Vitest+MSW):api client 注入会话凭证、401 触发重登清理;TanStack Query 的 query 加载态/mutation 成功后失效列表。先见红。
- [x] 4.2 实现 api client、auth context(admin Session token)、TanStack Query provider 与基础 hooks。跑 4.1 见绿。

## 5. 应用壳 + 路由 + 导航(含未迁移域深链 legacy)

- [x] 5.1 写测试:路由渲染、导航中未迁移域(如 providers)指向 `/admin/ui-legacy`。先见红。
- [x] 5.2 实现 React Router 应用壳、登录路由守卫、导航(agents 为原生页,其余域深链 legacy)。跑 5.1 见绿。

## 6. agents 域达 legacy parity(TDD)

- [x] 6.1 写测试(Vitest+MSW):agents 列表/创建/编辑/删除/启用禁用/归档恢复/克隆/版本激活,各调用对应 admin API、mutation 后列表失效刷新。先见红。
- [x] 6.2 实现 `features/agents/` 各页面与组件,逐能力对照 legacy parity。跑 6.1 见绿。

## 7. Playwright 登录→agents 端到端烟测

- [x] 7.1 把 2.2 的占位 e2e 填实:启动托管的 dist,Playwright 登录 → 进入 agents 页 → 断言列表渲染。本地/CI 跑通。

## 8. Change 收尾验证

- [x] 8.1 `make test-frontend` 全绿(vitest + 覆盖率阈值 + tsc + lint)。
- [x] 8.2 `make test-pr` 全绿 + `uv run pytest tests/integration -q`(对照 main 基线,含 3.1 托管测试)无新增失败。
- [x] 8.3 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` 通过;确认未碰 agent 运行时、未引入 agent→platform 反向依赖。
- [x] 8.4 手动核对:`/admin/ui` 新 SPA 能登录、agents 域与 legacy parity;`/admin/ui-legacy` 旧台全功能仍可达;未迁移域导航正确深链 legacy。
