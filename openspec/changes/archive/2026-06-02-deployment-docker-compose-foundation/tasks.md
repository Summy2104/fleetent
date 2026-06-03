# tasks

## 1. OpenSpec proposal

- [x] 1.1 创建 proposal、design、tasks 和 deployment / configuration spec delta
- [x] 1.2 运行 `openspec validate 2026-06-02-deployment-docker-compose-foundation --strict`

## 2. 配置初始化命令

- [x] 2.1 Write failing tests：`fleetent-admin init-config --dry-run` 输出将创建 `.env`、`config/settings.yaml`、`config/mcp.servers.yaml`、`data/`、`data/logs/`、`data/diagnostics/`、`secrets/`，且不写文件系统
- [x] 2.2 Verify red：运行 `uv run pytest tests/unit -x -q`，确认 init-config 测试失败
- [x] 2.3 Implement：在 `platform.admin_cli` 增加 `init-config` 命令和可测试的初始化 helper
- [x] 2.4 Verify green：运行 `uv run pytest tests/unit -x -q`
- [x] 2.5 Write failing tests：已存在文件时默认跳过并提示；`--force` 覆盖 generated files；未知文件不删除
- [x] 2.6 Verify red：运行 `uv run pytest tests/unit -x -q`
- [x] 2.7 Implement：补齐 skip / force 行为
- [x] 2.8 Verify green：运行 `uv run pytest tests/unit -x -q`

## 3. `.env`、secrets 和配置样例

- [x] 3.1 Write failing tests：`.env.example` 存在且不包含真实 secret；`.gitignore` 忽略 `.env` 和 `secrets/`
- [x] 3.2 Verify red：运行 `uv run pytest tests/integration/test_deployment_docs.py -x -q` 或新增对应部署文件测试并确认失败
- [x] 3.3 Implement：新增 `.env.example`，更新 `.gitignore`，新增 `secrets.example.md` 或 `docs/deployment/secrets.md`
- [x] 3.4 Verify green：运行相关文档 / 部署文件测试
- [x] 3.5 Write failing tests：`config/settings.yaml.example` 中 file credential_ref 示例使用 `/app/secrets/google-drive-token.json`，且 secrets 文件名不表达 scope
- [x] 3.6 Verify red：运行相关测试并确认失败
- [x] 3.7 Implement：更新 settings example
- [x] 3.8 Verify green：运行相关测试

## 4. Dockerfile / Compose / entrypoint

- [x] 4.1 Write failing tests：Dockerfile 包含 `scripts/`、config examples 和 entrypoint；容器端口为 `8765`
- [x] 4.2 Verify red：运行相关部署文件测试并确认失败
- [x] 4.3 Implement：更新 Dockerfile，复制 `scripts/` 和 config examples，配置 entrypoint
- [x] 4.4 Verify green：运行相关部署文件测试
- [x] 4.5 Write failing tests：`docker-compose.yml` 使用 `.env`、挂载 `data` / `config` / `secrets:ro`，映射 `8765:8765`
- [x] 4.6 Verify red：运行相关部署文件测试并确认失败
- [x] 4.7 Implement：更新 compose
- [x] 4.8 Verify green：运行相关部署文件测试
- [x] 4.9 Write failing tests：entrypoint 默认不运行 upgrade，`FLEETENT_AUTO_UPGRADE=true` 时才调用 `scripts/upgrade.py`
- [x] 4.10 Verify red：运行相关 unit tests 并确认失败
- [x] 4.11 Implement：新增 `scripts/docker_entrypoint.sh` 或等价可测入口
- [x] 4.12 Verify green：运行相关 unit tests

## 5. 旧配置文件清理

- [x] 5.1 Write failing tests：仓库不再跟踪 `config/mcp.yaml`，且 deployment docs 不要求旧 MCP 文件存在
- [x] 5.2 Verify red：运行相关配置 / 文档测试并确认失败
- [x] 5.3 Implement：删除 tracked `config/mcp.yaml`，保持 `config/mcp.servers.yaml.example`
- [x] 5.4 Verify green：运行相关测试

## 6. Deployment docs 和 runbook

- [x] 6.1 Write failing tests：deployment docs / runbook 将 Docker Compose 作为 Pilot 默认入口，端口统一 `8765`
- [x] 6.2 Verify red：运行 `uv run pytest tests/integration/test_deployment_docs.py -x -q`
- [x] 6.3 Implement：更新 `pilot-install-checklist.md`、`pilot-acceptance-guide.md`、`pilot-runbook.md` 和 deployment capability 文档
- [x] 6.4 Verify green：运行 `uv run pytest tests/integration/test_deployment_docs.py -x -q`

## 7. 验证与归档

- [x] 7.1 运行 `uv run ruff format src tests`
- [x] 7.2 运行 `uv run ruff check src tests`
- [x] 7.3 运行 `uv run mypy src`
- [x] 7.4 运行 `uv run pytest -x -q`
- [x] 7.5 如本机 Docker 可用，运行 `docker compose config`；可选运行 `docker compose build fleetent`
- [x] 7.6 运行 `openspec validate 2026-06-02-deployment-docker-compose-foundation --strict`
- [x] 7.7 运行 `git diff --check`
- [x] 7.8 所有 checkbox 完成后归档 change 并验证 `openspec/specs/deployment/spec.md` 和 `openspec/specs/configuration/spec.md`
