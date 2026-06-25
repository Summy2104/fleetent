## ADDED Requirements

### Requirement: platform init-config 支持 --home 参数

`fleetent platform init-config` SHALL 接受 `--home <path>` 参数，指定部署根目录。当 `--home` 未传入时，SHALL 使用 `FLEETENT_HOME` 环境变量（经 `paths.base_dir()` 解析）作为默认根。**不再**使用 `Path.cwd()` 作为隐含根。

目标文件已存在时 SHALL 跳过（打印 `skip`）；`--force` 时 SHALL 覆盖（打印 `overwrite`）。

#### Scenario: 指定 --home 初始化平台 env

- **WHEN** operator 运行 `fleetent platform init-config --home /opt/fleetent`
- **THEN** `/opt/fleetent/.env` 从 `.env.example` 模板创建（若不存在）
- **AND** `/opt/fleetent/platform.yaml` 从 `platform.yaml.example` 模板创建（若不存在）
- **AND** 标准目录 `logs/`、`diagnostics/`、`secrets/` 在 `/opt/fleetent/` 下创建

#### Scenario: 默认使用 FLEETENT_HOME

- **WHEN** operator 运行 `fleetent platform init-config`（不传 `--home`）且 `FLEETENT_HOME=/data/fleetent`
- **THEN** `/data/fleetent/.env` 从模板创建（若不存在）

#### Scenario: 文件已存在时跳过

- **WHEN** `/opt/fleetent/.env` 已存在，operator 运行 `fleetent platform init-config --home /opt/fleetent`
- **THEN** 命令输出 `skip .env`，文件内容不变

#### Scenario: --force 强制覆盖

- **WHEN** operator 运行 `fleetent platform init-config --home /opt/fleetent --force`
- **THEN** 命令输出 `overwrite .env`，文件被模板内容替换

---

### Requirement: fleetent node init-config 命令

系统 SHALL 提供 `fleetent node init-config` 命令，在 `$FLEETENT_HOME/node/` 下创建 `.env` scaffold（从 `node.env.example` 复制）。

生成的 `.env` SHALL 包含所有 node 进程变量的空占位（`FLEETENT_NODE_PLATFORM_URL`、`FLEETENT_NODE_ID`、`FLEETENT_NODE_SERVICE_KEY`、`FLEETENT_NODE_INTERVAL_SECONDS`、`FLEETENT_FORWARDER_HOST_OVERRIDE`），值均为空或默认。

命令 SHALL 在完成后打印提示：`FLEETENT_NODE_SERVICE_KEY` 需通过 `fleetent node register` / `dev_node_provision.py` 填入。

#### Scenario: 首次初始化 node env

- **WHEN** `$FLEETENT_HOME/node/.env` 不存在，operator 运行 `fleetent node init-config`
- **THEN** `$FLEETENT_HOME/node/.env` 被创建，含 node 进程变量占位
- **AND** 命令打印提示需填入 service key

#### Scenario: 已存在时跳过

- **WHEN** `$FLEETENT_HOME/node/.env` 已存在（含有效 service key），运行 `fleetent node init-config`
- **THEN** 命令输出 `skip node/.env`，文件内容不变，service key 不被清空

---

### Requirement: fleetent kb-worker init-config 命令

系统 SHALL 提供 `fleetent kb-worker init-config` 命令，在 `$FLEETENT_HOME/kb-worker/` 下创建 `.env` scaffold（从 `kb-worker.env.example` 复制）。

命令 SHALL 幂等，文件已存在时跳过（`--force` 覆盖）。

#### Scenario: 首次初始化 kb-worker env

- **WHEN** `$FLEETENT_HOME/kb-worker/.env` 不存在，operator 运行 `fleetent kb-worker init-config`
- **THEN** `$FLEETENT_HOME/kb-worker/` 目录被创建（若不存在），`.env` 从模板创建
- **AND** 文件内含 `FLEETENT_KB_WORKER_QUEUE_DATABASE_URL` 等占位

#### Scenario: 已存在时跳过

- **WHEN** `$FLEETENT_HOME/kb-worker/.env` 已存在，运行 `fleetent kb-worker init-config`
- **THEN** 命令输出 `skip kb-worker/.env`，文件内容不变
