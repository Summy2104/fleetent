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

- ✅ **pydantic-settings 配置体系**：.env + config/settings.yaml 双源加载
  - `config/settings.yaml` 是统一非敏感应用策略配置文件，环境变量和 `.env` 优先级高于 YAML
  - MCP server definitions 独立放在 `config/mcp.servers.yaml`；`settings.yaml` 只保留 `mcp.enabled` 这类全局策略
  - 密钥不进 YAML、不进 DB、不进 git，仅通过 env var 注入；YAML 中只保存 `api_key_env` 这类环境变量名引用
  - 旧 `config/mcp.yaml`、`config/cron.yaml`、`config/webhooks.yaml` 存在时启动 fail fast，避免静默使用过期配置

- ✅ **Dockerfile**：单容器部署
  - 当前已有 Dockerfile 和 docker-compose.yml，关键配置：
    - `extra_hosts: host.docker.internal:host-gateway`（Linux 宿主机访问，`fleetent.integrations.sandbox` 通过此地址调用宿主机工具进程）
    - `volumes: ./data:/app/data, ./config:/app/config`（持久化用户数据和配置）
    - `env_file: .env.production`（密钥通过 env_file 注入，不写入镜像）

- ✅ **alembic DB migration**：schema 版本管理
  - 升级脚本在 SQLite 备份成功后执行 `alembic upgrade head`，不需要手动改表

- ✅ **SQLite-first 默认存储**：无需独立数据库服务
  - 数据在 data/ 目录，挂载 volume 持久化
  - 当前不要求 PostgreSQL；数据库访问通过统一 DB runtime 边界，避免把业务层写死到 SQLite
  - `database_url` 默认指向 `sqlite:///data/fleetent.db`；非 SQLite backend 当前 fail fast
  - 存量本地 `data/users.db` 不会自动迁移、复制或 fallback；需要保留数据时由 operator 手动重命名为 `data/fleetent.db`，或选择重新初始化
  - 不引入 ORM；schema lifecycle 由 alembic 统一管理

- ✅ **observability 数据落点已明确**：运行观测数据按用途分层持久化
  - agent traces v1.0 使用 SQLite `traces` 表，通过 DB runtime 访问
  - 程序日志写入 `data/logs/` 下的日期文件，随 `data/` volume 持久化
  - logs / traces / diagnostics export 已支持手动 retention dry-run / apply，默认不自动清理
  - SQLite backups 不在 diagnostics retention 范围内，备份保留由部署方管理

- ✅ **SQLite 升级备份脚本**：`scripts/upgrade.py`
  - `--database-url` 优先于 `DATABASE_URL`，`DATABASE_URL` 优先于 `Settings().database_url`
  - 当前只支持本地 SQLite database URL；非 SQLite、远程 SQLite、`:memory:` 都会 fail fast
  - 默认备份写入 `data/backups/YYYYMMDD-HHMMSS/fleetent.db`
  - `--backup-dir` 可覆盖备份根目录，便于自定义部署和测试
  - `--dry-run` 只校验 database URL 并输出 backup / migration 计划，不要求 DB 文件存在，不创建备份，不运行 Alembic
  - `--backup-only` 只创建备份，不运行 Alembic
  - 非 dry-run 模式下 DB 文件不存在会 fail fast；backup 成功后才会运行 migration
  - migration 失败时不会自动 rollback；已创建 backup 会保留，脚本返回非 0

- ✅ **Pilot connector operations CLI**：`fleetent-admin kb connectors ...`
  - `list` 列出 settings 中的 Google Drive / Confluence connector 安全摘要
  - `check <connector_id>` 检查 `credential_ref` 与 remote scope，返回 credential_missing / credential_invalid / auth_failed / scope_unreachable / ok
  - `sync <connector_id> --dry-run` 生成同步计划，不写 KB、source state 或 vector index
  - `sync <connector_id>` 手动执行同步并写入最近一次 status
  - `status <connector_id>` 查询最近一次 dry-run / sync 结果；输出不包含 credential payload、token、secret 或文档正文

- ✅ **Diagnostics export / retention CLI**：`fleetent-admin diagnostics ...`
  - `export` 生成本地脱敏诊断包，包含 manifest、logs、trace / usage / performance 摘要、connector status、environment 和 config summary
  - `retention dry-run` 只展示将删除的 logs、traces 和 diagnostics export 包候选
  - `retention apply` 只有显式开启 `diagnostics.retention.enabled=true` 后才删除诊断数据
  - retention 不删除 memory、KB 文档 / chunks、connector source state、SQLite 主库或 SQLite backups

- ✅ **Observability admin query CLI**：`fleetent-admin observability ...`
  - `traces` 查询 agent run trace events，只输出事件元数据和 payload key summary
  - `usage` 查询 run count、token usage 和 by-model summary
  - `performance` 查询失败率、延迟、LLM / tool / fallback / permission 指标

- ✅ **Pilot install checklist**：[pilot-install-checklist.md](../deployment/pilot-install-checklist.md)
  - 覆盖前置条件、配置与 secret 边界、升级 / 备份、启动、健康检查、KB connector、observability、
    diagnostics、回滚、验收和问题上报包

- ✅ **Pilot acceptance guide**：[pilot-acceptance-guide.md](../deployment/pilot-acceptance-guide.md)
  - 用于安装完成后的测试环境人工验收，覆盖 Go / Conditional Go / No-Go 判定、SQLite restore drill、
    observability / diagnostics、memory、long-term context、reflection、KB local / SaaS connector、
    vector reindex、真实外部依赖 skipped / failed / passed 记录和验收报告模板

当前定位：已有本地开发和基础 Docker 部署地基，但还不是面向客户交付的一键 on-prem 安装包。

## 升级与恢复

本地 SQLite-first 部署升级入口：

```bash
uv run python scripts/upgrade.py
```

常用选项：

```bash
uv run python scripts/upgrade.py --dry-run
uv run python scripts/upgrade.py --backup-only
uv run python scripts/upgrade.py --database-url sqlite:///data/fleetent.db --backup-dir data/backups
```

如果 migration 失败，脚本不会自动 rollback。手动恢复步骤：

1. 停止 fleetent 服务。
2. 用脚本输出的 backup DB 文件替换当前 DB 文件，例如将 `data/backups/YYYYMMDD-HHMMSS/fleetent.db` 复制回 `data/fleetent.db`。
3. 重启 fleetent 服务。

## Connector 运维

Pilot 环境中，Google Drive / Confluence connector 的真实 credential 不写入 `settings.yaml`；配置文件只保存
`credential_ref`，例如 `file:///etc/fleetent/secrets/google-drive-token.json` 或
`env:FLEETENT_CONFLUENCE_API_TOKEN`。对应文件权限、环境变量注入和备份策略由部署方保护。

常用操作：

```bash
uv run fleetent-admin kb connectors list
uv run fleetent-admin kb connectors check eng-drive
uv run fleetent-admin kb connectors sync eng-drive --dry-run
uv run fleetent-admin kb connectors sync eng-drive
uv run fleetent-admin kb connectors status eng-drive
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
uv run fleetent-admin diagnostics export
uv run fleetent-admin diagnostics export --from 2026-06-02T00:00:00 --to 2026-06-02T23:59:59
```

诊断包默认写入 `data/diagnostics`。包内数据会二次脱敏，并排除 memory 内容、KB 文档正文 / chunks、
SQLite 主库、SQLite backups 和 connector credential 文件内容。

手动 retention：

```bash
uv run fleetent-admin diagnostics retention dry-run
uv run fleetent-admin diagnostics retention apply
```

默认 `diagnostics.retention.enabled=false`，因此 `apply` 会拒绝执行。只有在 `config/settings.yaml` 中显式
开启并设置对应 days 字段后，才会删除超过天数的 logs、traces 或 diagnostics export 包。SQLite backups
不在 diagnostics retention 范围内，备份保留策略由部署方单独管理。

## Observability 查询

Pilot 排障优先使用 admin CLI，不直接查询 SQLite：

```bash
uv run fleetent-admin observability traces --run-id run-1 --limit 20
uv run fleetent-admin observability traces --event-type agent_run_failed --from 2026-06-02T00:00:00 --to 2026-06-02T23:59:59
uv run fleetent-admin observability usage --user-id user-1 --limit 100
uv run fleetent-admin observability performance --agent-id agent-1 --limit 100
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
  - 默认值指向本机 `data/fleetent.db`
  - 业务 store 通过统一 DB runtime 获取连接和事务，不直接依赖 SQLite 文件路径

## 当前缺口

- 缺少完整安装包：初始化、配置校验、迁移、启动、健康检查未形成一键流程。
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
- Then：服务在 5 分钟内启动，GET /health 返回 200

**场景 2：版本升级**
- Given：运行中的 v1.0 实例，有存量用户数据
- When：执行升级脚本部署新版本
- Then：DB migration 自动执行，存量数据完整保留，服务正常启动

**场景 3：配置隔离**
- Given：.env 文件包含 ANTHROPIC_API_KEY
- When：服务运行
- Then：API key 不出现在任何日志、trace、system prompt 中

**场景 4：License 校验（v1.0）**
- Given：license key 绑定服务器 A 的 MAC 地址
- When：将服务部署到服务器 B
- Then：服务启动失败，输出 license 不匹配的错误

## 待决问题

- [ ] License key 的发放和管理方案（负责人：待认领）
- [ ] PostgreSQL 作为可选生产后端的时间节点与 OpenSpec change 范围（负责人：待认领）
