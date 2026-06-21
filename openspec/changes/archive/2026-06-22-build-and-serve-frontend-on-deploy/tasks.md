> TDD 硬门禁:可单测的先写测试见红 → 实现见绿(server dist 解析);脚本/CI 步以集成或手动验证为主。合并:本切片可由窗口自合(改 scripts/CI/server.py,与在跑的 E/F 零重叠)或交主会话——按当前约定。

## 1. server.py dist 路径 env 可覆盖(TDD)

- [x] 1.1 写测试(integration,FastAPI):设 `FLEETENT_ADMIN_UI_DIST` 指向含 index.html 的临时 dist → `/admin/ui` 服务它;未设且默认路径无 dist → 503 清晰报错;设但目录无 dist → 503。先见红。
- [x] 1.2 实现 `server.py`:`ADMIN_UI_DIST_DIR` 改 `os.environ.get("FLEETENT_ADMIN_UI_DIST") or <parents[2]/frontend/dist>`;503 文案保留。跑 1.1 见绿。

## 2. install-platform.sh 构建 SPA

- [x] 2.1 在 `install-platform.sh` 装 binary 后增构建步:`make frontend-install && make frontend-build`;node/yarn 缺失则按 nodesource(setup_22 + corepack)装,或明确报错 + 指引(不静默跳过);更新尾部启动指引。
- [x] 2.2 验证(手动/脚本干跑):干净环境跑 install-platform.sh 后 `frontend/dist/index.html` 存在,`uvicorn fleetent.server:app` 起来后 `/admin/ui` 返回 SPA(非 503)。

## 3. CI 验 build

- [x] 3.1 `bitbucket-pipelines.yml` 的 frontend gate 增 `make frontend-build`(test 之外);确认 build 失败能 fail CI。

## 4. Change 收尾验证

- [x] 4.1 `make test-pr` + `make test-unit-ci` 全绿;新增 server dist 集成测试通过(对照 main 基线无新增失败)。
- [x] 4.2 `make test-frontend` + `make frontend-build` 本地全绿。
- [x] 4.3 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` 通过。
- [x] 4.4 手动:干净装一遍(install-platform.sh)→ 起平台 → `/admin/ui` 出新 SPA,确认"生产没 UI"已堵。
