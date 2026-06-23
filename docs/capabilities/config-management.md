# deployment

> 写作提醒：功能描述只写可观察的行为，不写内部实现细节。验收标准只写端到端可验证的行为。

## 概述

让 fleetent 能安全、可重复地部署到客户自己的服务器上，并在版本升级时不丢数据。

**负责**：容器化打包（Docker）、环境变量与配置文件加载、数据库 schema 版本管理（alembic）、on-premises 安装包与 license 校验。

**不负责**：运行时业务逻辑（→ 各模块）、IM 平台网络连接（→ im-gateway）、用户认证（→ user_store）。

**调用关系**：
- 依赖：config、alembic（DB migration）
- 被依赖：所有模块（运行时依赖配置）

## 现状

- ✅ **Platform home 配置体系**：根目录 `.env` + `platform.yaml` 保存平台级 env 和非敏感配置；
  `agents/<agent-id>/.env` + `agents/<agent-id>/agent.yaml` 保存 Agent 运行配置
  - `agents/<agent-id>/agent.yaml` 是部署 agent 的非敏感运行配置文件，保存 agent、model、MCP servers、knowledge binding、connector、embedding、rerank 等配置
  - 密钥不进 YAML、不进 DB、不进 git，仅通过 env var 注入；YAML 中只保存 `api_key_env`、`*_env` 这类环境变量名引用
  - `config/` 不再是部署配置或模板命名空间；MCP 定义来自 Platform DB / materialized Agent config

- ✅ **Docker Compose**：Pilot 默认部署入口
  - Pilot 默认从 `docker compose run --rm fleetent uv run fleetent admin init-config` 开始，
    显式执行 `scripts/upgrade.py` 后再 `docker compose up -d`。
  - `uv run uvicorn fleetent.server:app` 只作为开发模式保留，不作为 Pilot 默认部署入口。
  - 当前 Dockerfile 和 docker-compose.yml 关键配置：
    - `extra_hosts: host.docker.internal:host-gateway`（Linux 宿主机访问，`fleetent.integrations.sandbox` 通过此地址调用宿主机工具进程）
    - `volumes: ./data:/app/data, ./agents:/app/agents, ./platform.yaml:/app/platform.yaml, ./secrets:/app/secrets:ro`
      （持久化用户数据、Agent homes、平台配置，secret 文件只读挂载）
    - `env_file: .env`（本地 `.env` 由 init-config 从 `.env.example` 生成，不写入镜像）
    - `ports: 8765:8765`

- ✅ **alembic DB migration**：schema 版本管理
  - 升级脚本在 SQLite 备份成功后执行 `alembic upgrade head`，不需要手动改表

- ✅ **SQLite-first 默认存储**：无需独立数据库服务
  - 数据在 data/ 目录，挂载 volume 持久化
  - 当前不要求 PostgreSQL；数据库访问通过统一 DB runtime 边界，避免把业务层写死到 SQLite
  - `database_url` 默认指向 `sqlite:///<FLEETENT_HOME>/management.db`（管理库文件名与概念名对齐）；非 SQLite backend 当前 fail fast
  - 本 change 不做旧布局或旧文件名自动迁移；显式 `DATABASE_URL` 仍可指向自定义文件名
  - 需要保留旧布局数据时由 operator 自行迁移或重建 tenant-first home
  - 不引入 ORM；schema lifecycle 双权威（按库分）：**管理库** = Alembic；**agent 侧库**（per-agent / 共享记忆 / KB）= 嵌入式 forward-only 迁移（Y，`user_version` migrate-on-open），不经 Alembic

- ✅ **observability 数据落点已明确**：运行观测数据按用途分层持久化
  - agent traces v1.0 使用 SQLite `traces` 表，通过 DB runtime 访问
  - 程序日志写入 `data/logs/` 下的日期文件，随 `data/` volume 持久化
  - logs / traces / diagnostics export 已支持手动 retention dry-run / apply，默认不自动清理
  - SQLite backups 不在 diagnostics retention 范围内，备份保留由部署方管理

- ✅ **SQLite 升级备份脚本**：`scripts/upgrade.py`
  - `--database-url` 优先于 `DATABASE_URL`，`DATABASE_URL` 优先于 `Settings().database_url`
  - 当前只支持本地 SQLite database URL；非 SQLite、远程 SQLite、`:memory:` 都会 fail fast
  - **备份覆盖数据目录下全部物理库**（持久层 #3）：递归枚举 `data/` 下任意深度的 `*.db`（管理库 + per-tenant 的 KB / 共享记忆库 + per-agent 运行库 + 各向量库），逐库经统一 `db.py` 入口执行 `PRAGMA wal_checkpoint(TRUNCATE)` 后复制（含 `-wal`/`-shm` sidecar），避免 WAL 中未落盘的写丢失
  - 备份写入 `data/backups/YYYYMMDD-HHMMSS/`，按原数据目录相对结构**镜像**每一个库（含 `<tenant>/` 与 `<tenant>/<agent_id>/` 子目录）
  - 备份发现以递归扫文件为主、管理库 registry（tenants）兜底交叉核对：登记但目录缺失的主体以告警形式提示，停机 agent 的库仍被递归发现并备份
  - `--backup-dir` 可覆盖备份根目录，便于自定义部署和测试
  - `--dry-run` 只校验 database URL 并输出 backup / migration 计划，不要求 DB 文件存在，不创建备份，不运行 Alembic
  - `--backup-only` 只创建备份（同样覆盖全部物理库），不运行 Alembic
  - 非 dry-run 模式下管理库文件不存在（且无可迁移的旧 `fleetent.db`）会 fail fast；backup 成功后才会运行 migration
  - migration 失败时不会自动 rollback；已创建 backup 会保留，脚本返回非 0
  - 备份语义假定 upgrade 运行在停服 / 静默窗口（与既有 upgrade 语义一致），非在线一致性快照

- ✅ **Pilot connector operations HTTP API**：`/admin/kb/connectors/*`
  - `list` 列出 Platform Knowledge config / DB snapshot 中的 Google Drive / Confluence connector 安全摘要
  - `check <connector_id>` 检查 `credential_ref` 与 remote scope，返回 credential_missing / credential_invalid / auth_failed / scope_unreachable / ok
  - `sync <connector_id> --dry-run` 生成同步计划，不写 KB、source state 或 vector index
  - `sync <connector_id>` 手动执行同步并写入最近一次 status
  - `status <connector_id>` 查询最近一次 dry-run / sync 结果；输出不包含 credential payload、token、secret 或文档正文

- ✅ **Diagnostics export / retention CLI**：`fleetent admin diagnostics ...`
  - `export` 生成本地脱敏诊断包，包含 manifest、logs、trace / usage / performance 摘要、connector status、environment 和 config summary
  - `retention dry-run` 只展示将删除的 logs、traces 和 diagnostics export 包候选
  - `retention apply` 只有显式开启 `diagnostics.retention.enabled=true` 后才删除诊断数据
  - retention 不删除 memory、KB 文档 / chunks、connector source state、SQLite 主库或 SQLite backups

- ✅ **Observability admin query HTTP API**：`/admin/observability/{traces,usage,performance}`
  - `traces` 查询 agent run trace events，只输出事件元数据和 payload key summary
  - `usage` 查询 run count、token usage 和 by-model summary
  - `performance` 查询失败率、延迟、LLM / tool / fallback / permission 指标

- ✅ **Pilot install checklist**：[pilot-install-checklist.md](../operations/pilot-install-checklist.md)
  - 覆盖前置条件、配置与 secret 边界、升级 / 备份、启动、健康检查、KB connector、observability、
    diagnostics、回滚、验收和问题上报包

- ✅ **Pilot acceptance guide**：[pilot-acceptance-guide.md](../operations/pilot-acceptance-guide.md)
  - 用于安装完成后的测试环境人工验收，覆盖 Go / Conditional Go / No-Go 判定、SQLite restore drill、
    observability / diagnostics、memory、long-term context、reflection、KB local / SaaS connector、
    vector reindex、真实外部依赖 skipped / failed / passed 记录和验收报告模板

当前定位：已有本地开发和基础 Docker 部署地基，但还不是面向客户交付的一键 on-prem 安装包。

## 升级与恢复

Docker Compose first 的 SQLite-first 部署升级入口：

```bash
docker compose run --rm fleetent uv run python scripts/upgrade.py
```

常用选项：

```bash
docker compose run --rm fleetent uv run python scripts/upgrade.py --dry-run
docker compose run --rm fleetent uv run python scripts/upgrade.py --backup-only
docker compose run --rm fleetent uv run python scripts/upgrade.py --database-url sqlite:////app/management.db --backup-dir data/backups
```

如果 migration 失败，脚本不会自动 rollback。手动恢复步骤（覆盖多物理库）：

1. 停止 fleetent 服务。
2. 用同一个备份批次目录 `data/backups/YYYYMMDD-HHMMSS/` 整体替换数据目录下对应的全部库文件——按镜像结构把每个库（含 `tenants/<tenant>/agents/<agent>/data/` 下的库及其 `-wal`/`-shm` sidecar）复制回各自位置，例如将 `data/backups/YYYYMMDD-HHMMSS/management.db` 复制回 `<FLEETENT_HOME>/management.db`。
3. 重启 fleetent 服务。

务必使用**同一个备份批次**的各库，保证恢复后多库互相一致，不要混用不同时间点的备份。

## Connector 运维

Pilot 环境中，Google Drive / Confluence connector 的真实 credential 不写入 `agents/<agent-id>/agent.yaml`；
配置文件只保存平铺的环境变量名引用，例如 `FLEETENT_GOOGLE_DRIVE_ACCESS_TOKEN` 和
`FLEETENT_CONFLUENCE_TOKEN`。对应环境变量注入、文件权限和备份策略由部署方保护。

常用操作：

```bash
GET /admin/kb/connectors
POST /admin/kb/connectors/eng-drive/check
POST /admin/kb/connectors/eng-drive/sync  # body: {"dry_run": true}
FLEETENT_GOOGLE_DRIVE_EXECUTE_SYNC=1 \
  POST /admin/kb/connectors/eng-drive/sync  # body: {"dry_run": false}
GET /admin/kb/connectors/eng-drive/status
```

排障方向：

- `credential_missing`：检查 `credential_ref` 指向的文件是否存在，或环境变量是否已注入服务进程。
- `credential_invalid`：检查 credential 文件格式或 env var 内容，不要把真实 payload 复制到日志或 issue。
- `auth_failed`：重新授权或轮换外部 SaaS credential，再运行 `check`。
- `scope_unreachable`：检查 folder / space / page id、connector 账号权限和企业网络出口。
- `sync_failed`：先查看 `status` 的脱敏失败摘要，再用 `--dry-run` 缩小失败范围。

## Diagnostics 与 Retention

诊断包导出：

```bash
uv run fleetent admin diagnostics export
uv run fleetent admin diagnostics export --from 2026-06-02T00:00:00 --to 2026-06-02T23:59:59
```

诊断包默认写入 `data/diagnostics`。包内数据会二次脱敏，并排除 memory 内容、KB 文档正文 / chunks、
SQLite 主库、SQLite backups 和 connector credential 文件内容。

手动 retention：

```bash
uv run fleetent admin diagnostics retention dry-run
uv run fleetent admin diagnostics retention apply
```

默认 `diagnostics.retention.enabled=false`，因此 `apply` 会拒绝执行。只有在配置中显式
开启并设置对应 days 字段后，才会删除超过天数的 logs、traces 或 diagnostics export 包。SQLite backups
不在 diagnostics retention 范围内，备份保留策略由部署方单独管理。

## Observability 查询

Pilot 排障优先使用 admin HTTP API，不直接查询 SQLite：

```bash
GET /admin/observability/traces?run_id=run-1&limit=20
GET /admin/observability/traces?event_type=agent_run_failed&since=2026-06-02T00:00:00&until=2026-06-02T23:59:59
GET /admin/observability/usage?user_id=user-1&limit=100
GET /admin/observability/performance?agent=agent-1&limit=100
```

`traces` 输出只包含 trace 元数据和 payload key summary，不输出 prompt、reply、tool payload 或 credential
原值。`usage` 和 `performance` 通过 observability public API 聚合数据，不直接访问 `traces` 表。

## 规划中（v1.0）

- [ ] **on-premises 安装包**：完整的一键部署方案
  - docker-compose.yml + .env.example + 安装文档
  - 包含启动前检查（端口、权限、环境变量）

- [ ] **License key 机制**：绑定目标服务器（MAC / CPU ID）
  - 启动时校验 license，不通过则拒绝启动
  - 阶段一：硬件绑定；阶段二：Nuitka 编译保护源码

- [ ] **多环境配置**：dev / staging / prod 配置文件分离
  - 通过 FLEETENT_ENV 环境变量切换

- [x] **升级脚本**：新版本部署时执行 `alembic upgrade head`
  - 升级前自动备份 SQLite 文件；migration 失败不自动 rollback

- ✅ **统一 database_url 配置**：以 SQLite 为默认后端，保留后续 PostgreSQL 接入空间
  - 默认值指向本机 `<FLEETENT_HOME>/management.db`
  - 业务 store 通过统一 DB runtime 获取连接和事务，不直接依赖 SQLite 文件路径

## 当前缺口

- Docker Compose 已作为 Pilot 默认入口；完整 release 安装包和镜像发布流水线仍未覆盖。
- 升级脚本已覆盖本地 SQLite backup / migration；完整发布包和自动 rollback 不在当前范围内。
- 日志 / trace / diagnostics export 已有手动 retention；SQLite backups 自动保留策略仍由部署方管理。
- License key 机制未设计。
- PostgreSQL 可选后端未实现，仅保留边界。

## 下一批候选 specs

- `deployment-onprem-install-package`
- `deployment-backup-retention-policy`
- `deployment-license-key`
- `database-postgresql-adapter`

## 自动化效果验证缺口

- 在临时目录中跑 install / upgrade smoke test，验证配置、migration、启动诊断。
- 用 docker compose fixture 验证服务能启动、健康检查通过、日志和数据库路径可写。
- 验证升级脚本在失败时不会破坏已有 SQLite 数据。

## 服务化 / 目录边界判断

deployment 本身不是业务服务，但会决定未来哪些模块可以外置。当前应先沉淀 scripts / packaging /
config validation 目录，服务拆分要等运行模块边界稳定后再做。

## 验收标准

**场景 1：首次部署**
- Given：一台干净的 Linux 服务器，安装了 Docker
- When：按照安装文档执行部署命令
- Then：服务在 5 分钟内启动，`curl -fsS http://127.0.0.1:8765/health` 返回 200

**场景 2：版本升级**
- Given：运行中的 v1.0 实例，有存量用户数据
- When：执行升级脚本部署新版本
- Then：DB migration 自动执行，存量数据完整保留，服务正常启动

**场景 3：配置隔离**
- Given：Agent `.env` 文件包含 `FLEETENT_MODEL_PRIMARY_API_KEY`
- When：服务运行
- Then：API key 不出现在任何日志、trace、system prompt 中

**场景 4：License 校验（v1.0）**
- Given：license key 绑定服务器 A 的 MAC 地址
- When：将服务部署到服务器 B
- Then：服务启动失败，输出 license 不匹配的错误

## 待决问题

- [ ] License key 的发放和管理方案（负责人：待认领）
- [ ] PostgreSQL 作为可选生产后端的时间节点与 OpenSpec change 范围（负责人：待认领）
