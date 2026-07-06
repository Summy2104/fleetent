## Context

Fleetent 已形成清晰的运行面边界：

- `fleetent agent run`：agent runtime 原语，node 拉起 agent 时使用。
- `fleetent node start`：agent host supervisor。
- `fleetent kb worker`：KB ingest worker。
- `fleetent chat`：终端客户端。

缺口是 Platform/control-plane：CLI namespace 仍叫 `admin`，启动仍靠 uvicorn 裸命令，
升级仍靠脚本或 Alembic 命令。用户心智上“Platform”与“Admin”混用，会在 UI、架构、
CLI、Makefile 之间形成额外映射。

## Goals / Non-Goals

**Goals**：
- 用 `fleetent platform ...` 统一 Platform/control-plane 本地入口。
- 不保留 `fleetent admin` alias，清掉历史包袱。
- 收口 platform serve / upgrade，消除 Makefile 和文档里的裸 uvicorn / 裸 upgrade 脚本主路径。
- 保持 agent/node/kb-worker 的懒加载与依赖边界。

**Non-Goals**：
- 不迁移 HTTP `/admin/*` 或 `/admin/ui` 路径。
- 不重命名权限角色 `admin` / `built_in_admin`。
- 不改变已有 Platform API 权限模型。
- 不做 dev stack 自动 bootstrap（可在后续 change 处理）。

## Decisions

### D1：CLI namespace 直接从 admin 改成 platform，不做 alias

`fleetent platform` 是唯一控制面 CLI namespace。`fleetent admin` 返回普通未知命令错误。
这样新旧心智不会并存，测试和文档能强制收敛。

角色语义保留：API 中的 `admin` role、built-in admin 用户、文档中表示角色的
“admin user” 不迁移。

### D2：代码包迁移为 platform_cli

将 `src/fleetent/platform/admin_cli/` 迁移到 `src/fleetent/platform/platform_cli/`。
`__main__.py` 只在 `argv[0] == "platform"` 时懒加载该入口。

不保留 `platform.admin_cli` re-export shim。理由与 CLI 一致：本项目当前选择清理历史包袱，
而不是继续承载双命名。

### D3：serve 是 uvicorn 的薄封装

`fleetent platform serve` 负责解析 `--host`、`--port`、`--reload`，然后调用 uvicorn
运行 `fleetent.server:app`。它不把 server 生命周期逻辑搬进 CLI。

Makefile、Docker entrypoint、安装脚本 next steps 全部改用 `fleetent platform serve`。
`uvicorn fleetent.server:app` 技术上仍可用（ASGI app 公开不变），但不再作为用户文档主入口。

### D4：upgrade 复用现有 scripts/upgrade.py 语义

`fleetent platform upgrade` 应与 `scripts/upgrade.py` 参数和行为一致：定位 SQLite 管理库、
备份全部物理库、legacy rename、运行 Alembic、backfill default agent flags。实现可以：

- 抽出 `scripts/upgrade.py` 中可复用函数到 `fleetent.platform.platform_cli.upgrade`；或
- 在 CLI 中调用现有 `scripts.upgrade.main`（若 import 路径可靠）。

用户入口必须是 `fleetent platform upgrade`；`scripts/upgrade.py` 可短期保留给 Docker/旧
运维内部调用，但文档主路径要迁移。

### D5：OpenAPI/HTTP 路径先不动

`/admin/*` 在当前系统中既是前端/API 路径，也是权限含义的一部分。迁移它会触碰前端路由、
大量集成/e2e 测试、外部链接和 OIDC redirect URI。这个风险不服务于“CLI 入口统一”的目标，
所以留到后续单独设计。

## Risks / Trade-offs

- **Breaking change**：所有脚本里的 `fleetent admin ...` 都会失效。缓解：同一 change
  内更新 Makefile、install scripts、Docker entrypoint、README、operations docs 和测试。
- **包名迁移大面积改动**：测试和 imports 会集中变化。缓解：只迁移 CLI 包，不动 `*_admin_api`
  / `*_admin_store` 这类 HTTP/API 内部命名，避免扩大范围。
- **serve wrapper 引入 uvicorn 依赖路径**：项目本来已依赖 uvicorn 启动；CLI 只薄封装，
  测试用 monkeypatch 验证调用参数，不在 unit 中真起服务。
- **upgrade 入口双存**：`scripts/upgrade.py` 短期保留可能仍被发现。缓解：文档与 Makefile
  主路径改为 `fleetent platform upgrade`；脚本作为底层/容器兼容载体，不再作为用户入口。
