## Why

平台管理前端目前是**单个 4731 行手写的 `static/admin.html`**(1 个 `<script>` + 1 个 `<style>`、343 个内联 JS 函数、无框架、无构建、无测试)。它无法并行开发(任何两条 UI 工作流都改同一文件必冲突)、编辑易错、且没有任何前端测试守护——而平台侧还有大量管理能力缺 UI(provider/MCP/connector 不能改删、KB 灌库、IM 群组、默认 agent、节点、租户均无页面)。继续往这个单体里堆功能只会让问题复利。本切片(C1)立起一个 **React + TypeScript + Vite 的 SPA 工程地基 + 完整测试栈与 TDD 门禁**,并把第一个域(agents)以 TDD 方式迁到与旧版 parity,作为后续各域可并行迁移的范式与底座。

## What Changes

- **新增 `frontend/` 工程**:Vite + React 18 + TypeScript。纯客户端 SPA,消费现有 admin REST API。
- **构建与托管**:构建期 `yarn build` 产出静态 `dist/`(gitignore;CI/打包期构建,**运行时无 Node**);FastAPI 在 `/admin/ui` 托管该 SPA 并提供 SPA fallback 路由。
- **新旧共存**:旧 `static/admin.html` 移到 `/admin/ui-legacy` 继续可用,直到所有域迁完后(后续 change)删除。**BREAKING**:`/admin/ui` 的服务内容从旧单体切换为新 SPA(本切片仅 agents 域达 parity,其余域在新 UI 中暂以入口占位 + "见 legacy" 指引,不破坏 legacy 可达)。
- **应用骨架**:认证(admin Session token context,401→重登)、路由(React Router)、服务端状态层(TanStack Query:缓存 + mutation 后失效)、组件层(shadcn/ui + Tailwind,自包含无运行时外链)。
- **测试栈(一等交付,先于功能代码)**:Vitest + @testing-library/react + jsdom(组件/hook)、MSW(mock admin API)、Playwright 登录→agents 烟测(真实托管链路)。包管理用 **yarn**。
- **门禁接线**:新增 `make test-frontend`(`vitest run` + `tsc --noEmit` + lint),**接进 PR 门禁**;设前端覆盖率阈值并在 CI 硬卡。前端按 **TDD 硬门禁**开发(测试任务先于实现任务)。
- **第一个域 agents**:在新 SPA 中以 TDD 实现 agents 列表/创建/编辑/删除/启停等,与旧版 parity,作为后续各域照抄的范式。

不在本切片:skills / kb / providers / connectors / mcp / nodes / tenancy / users / sessions 等域的完整迁移——留作后续可并行的 change(C2..Cn,每个域顺带补齐 pillar-2 的改删/缺失页);旧 `admin.html` 的最终删除也留到最后一个域迁完的 change。

## Capabilities

### New Capabilities
- `admin-frontend-spa`: 平台管理控制台的 SPA 前端工程与交付契约——React+TS+Vite 构建为静态资源由 FastAPI 托管、SPA fallback、与 legacy 共存的切换、认证/会话流、前端测试栈与 TDD 纪律,以及 agents 域达 legacy parity。

### Modified Capabilities
- `ci-quality-gate`: PR 门禁新增前端检查——`make test-frontend`(Vitest 单测 + 覆盖率阈值 + `tsc --noEmit` 类型检查 + lint)必须在 CI 中真实运行且为绿;前端改动同样被 gate。

## Impact

- **新增代码**:仓库根 `frontend/`(package.json / tsconfig / vite.config / 测试配置 / `src/**`);`Makefile` 增 `test-frontend` 等目标;CI 配置增前端步骤;`.gitignore` 增 `frontend/dist`、`node_modules`。
- **改动代码**:`src/fleetent/server.py`(及/或 platform 静态托管接线)——`/admin/ui` 改服务新 SPA dist + SPA fallback,旧 `admin.html` 迁 `/admin/ui-legacy`。
- **公共 API 表面**:基本只消费现有 admin REST API;至多补 1-2 个小端点(若 agents 域 parity 需要),不改既有契约。
- **模块边界**:`frontend/` 为新顶层;**不碰 agent 运行时(`runtime`/`session`/`im_gateway`/…)、不新增或修改管理表、不破坏 agent↔platform 单向解耦契约**。验证基线(无 platform 时 agent 仍能 `agent run`)不受影响。
- **依赖**:本仓首次引入 Node/yarn 工具链(仅构建期与 CI;运行时交付物仍为纯静态 + Python)。
- **测试**:首次引入前端测试栈(Vitest/Testing Library/MSW/Playwright);Python 侧测试不受影响。
