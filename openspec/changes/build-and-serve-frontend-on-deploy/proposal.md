## Why

整个 React 前端重写在**生产里看不见**:`scripts/install-platform.sh` 只装 binary + alembic + seed,**从不构建前端**;`frontend/dist` 是 gitignore、wheel 也没打包它;`server.py` 还按仓库相对路径 `parents[2]/frontend/dist` 找 dist。结果——装出来的平台 `/admin/ui` 返回 **503 "admin frontend dist not built"**。这是交付阻断:UI 做完了却发不出去。

## What Changes

- **A · install 构建 SPA**:`install-platform.sh` 增加构建步——`make frontend-install && make frontend-build`(产 `frontend/dist`),并处理 node/yarn 前置(缺则按 nodesource 装,或明确报错给指引,参照 CI frontend-gate 的装 node 方式)。更新安装后"启动平台"指引。
- **B · dist 路径稳健可覆盖**:`server.py` 的 admin UI dist 目录改为**可经 `FLEETENT_ADMIN_UI_DIST` 环境变量覆盖**,默认仍为仓库相对路径;dist 不存在时保留清晰 503。让部署能显式指向已构建的 dist,不再死依赖 cwd/导入位置。
- **C · CI 验证可构建**:CI 增加 `make frontend-build`(当前 gate 只跑 vitest/tsc/lint,**不跑 build**——vite build 坏了 gate 抓不到)。验证可交付产物真能 build。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `install-platform-script`: 安装流程新增"构建前端 SPA dist(yarn build)"+ node 前置,使部署后平台能直接服务 `/admin/ui`。
- `admin-frontend-spa`: 部署态服务契约——平台 SHALL 服务已构建的 dist;dist 目录可经 `FLEETENT_ADMIN_UI_DIST` 覆盖(默认仓库相对);未构建时返回清晰 503 而非空白。
- `ci-quality-gate`: 前端门禁新增 `make frontend-build`,验证可交付产物能构建(不只测试)。

## Impact

- **改动**:`scripts/install-platform.sh`(构建步 + node 前置 + 启动指引);`src/fleetent/server.py`(dist 路径 env 覆盖);`bitbucket-pipelines.yml`(frontend gate 加 build);`Makefile`(已有 frontend-build,可能加聚合 target)。
- **前置**:install/部署主机需 node/yarn(脚本处理或明确指引)。
- **边界**:不碰 agent 运行时;改 platform server 的静态托管路径解析 + 安装脚本 + CI。**与正在跑的 E(features/agents)/ F(node/reconcile)零文件重叠**,可并行。
- **不在本切片**:把 `frontend/dist` 打进 wheel 以支持 `uv tool`-only(无仓库)部署——on-prem 仓库式部署用 A+B 已足;若日后要纯 tool 分发再单独做(force-include + importlib.resources)。
