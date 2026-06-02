# 设计：Pilot install checklist

## 文档结构

`docs/deployment/pilot-install-checklist.md` 使用中文 runbook 形式，按 operator 执行顺序组织：

1. 适用范围与非目标。
2. 前置条件。
3. 配置与 secret 边界。
4. 安装 / 升级与备份。
5. 启动与健康检查。
6. Knowledge-base connector 验证。
7. Observability 查询。
8. Diagnostics export / retention。
9. 回滚。
10. Pilot 验收清单。
11. 问题上报包。

## 测试策略

新增 `tests/integration/test_deployment_docs.py`，读取 checklist 文档并断言：

- 文件存在。
- 包含关键章节标题。
- 包含 `scripts/upgrade.py --dry-run`、`alembic upgrade head`、`uv run uvicorn`、
  `fleetent-admin kb connectors ...`、`fleetent-admin observability ...`、`fleetent-admin diagnostics ...`
  等关键命令。
- 明确禁止把真实 secret / token / credential payload 写入 settings、日志、trace、diagnostics package 或 issue。
- 包含 rollback、backup restore、health check 和 pilot acceptance checklist。

## 模块边界

- owning package：`deployment`。
- public API surface：无。
- owned tables：无。
- config namespace：无新增；只引用现有配置。
- cross-module dependencies：文档引用 `scripts/upgrade.py`、`fleetent-admin` 子命令和 `/health` endpoint。
- migration / shim plan：无。
