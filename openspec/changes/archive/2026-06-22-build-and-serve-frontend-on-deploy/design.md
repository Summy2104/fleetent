## Context

`install-platform.sh`:`uv tool install --from $REPO_ROOT fleetent` + alembic + seed,然后打印让运维 `uvicorn fleetent.server:app` 启动——**没构建前端**。`frontend/dist` gitignore、wheel 未打包;`server.py` `ADMIN_UI_DIST_DIR = parents[2]/frontend/dist`(仓库相对)+ 未构建时 503。CI 只有 frontend-gate(vitest/tsc/lint),无 build 步、无部署步。dev(`make platform` 从仓库跑)能找到 dist,生产装出来找不到。

## Goals / Non-Goals

**Goals:** 部署后平台能服务新 SPA(`/admin/ui` 不再 503);install 构建 dist;dist 位置稳健可覆盖;CI 验证 build。
**Non-Goals:** 不把 dist 打进 wheel(uv-tool-only 部署,延后);不改 agent 运行时;不动 E/F 的文件。

## Decisions

**D1 · install 构建 dist + node 前置。** `install-platform.sh` 在装 binary 后、起服务前跑 `make frontend-install && make frontend-build`。node/yarn:检测缺失则按 CI 同款(nodesource setup_22 + corepack)装,或在无法安装时明确报错 + 指引(不静默跳过)。更新脚本尾部"启动平台"段提示 dist 已就绪。

**D2 · dist 路径 env 可覆盖。** `server.py`:`ADMIN_UI_DIST_DIR = Path(os.environ.get("FLEETENT_ADMIN_UI_DIST") or <parents[2]/frontend/dist>)`。部署可显式指向构建产物,摆脱对 cwd/导入位置的隐式依赖;未构建/不存在仍返回清晰 503(保留)。legacy admin.html 路径不动(将由 retire-legacy 切片处理)。

**D3 · CI 验 build。** frontend gate(或新增一步)跑 `make frontend-build`——tsc/vitest 抓不到 vite build 期问题(如资源/导入解析),build 步能。让"可交付产物能构建"成为门禁的一部分。

**D4 · 暂不打包进 wheel。** on-prem 是仓库式部署(clone + install-platform.sh + 从仓库 `uvicorn`),A+B 足够。纯 `uv tool` 无仓库分发再单独做(hatch force-include `frontend/dist` + `importlib.resources` 解析)——本切片只留 env 覆盖这个口子。

## Risks / Trade-offs

- **[install 主机无 node]** → 脚本按 CI 同款装 node,或明确报错 + 指引;不静默让 503 复现。
- **[构建拖慢 install]** → 一次性、可缓存(yarn.lock 锁);可接受。
- **[dist 过期]** → install/升级即重 build;`FLEETENT_ADMIN_UI_DIST` 指向最新产物。
- **[与 E/F 并行]** → 改 server.py(静态托管路径)/ install / CI,E(features/agents)、F(node)不碰这些;若 server.py 偶有相邻改动,合并冲突面也极小。
