## Why

当前配置布局已经出现三类不一致：

- 仓库模板在 `config/platform/` 与 `config/agent/`，但运行实例在 repo root /
  `FLEETENT_HOME` 下的 `.env`、`agents/<id>/agent.yaml`、`agents/<id>/.env`。
- `config/` 被当成“模板目录”，但历史 spec / loader 仍把 `config/settings.yaml`、
  `config/knowledge.yaml` 当作运行实例配置路径。
- Knowledge 默认 embedded 于 Platform，但 `knowledge.yaml` loader、materialize 和 spec
  仍保留独立文件语义，导致删除模板后配置内容没有自然归宿。

我们已经决定把 repo root / `FLEETENT_HOME` 定义为 Platform home。根目录承载 Platform
实例配置与 ENV，`agents/<agent-id>/` 承载 Agent 实例配置与 ENV。这样 `.example` 与实际文件
可以同目录，`config/` 不再承担配置模板目录职责。

## What Changes

- 移除 `config/` 作为 canonical 配置模板目录。
- 将 Platform 模板移动到 root：
  - `.env.example`
  - `platform.yaml.example`
- 将默认 Agent 模板移动到默认 Agent home 目录：
  - `agents/default/agent.yaml.example`
  - `agents/default/.env.example`
- 运行实例布局统一为：
  - `.env`
  - `platform.yaml`
  - `agents/<agent-id>/agent.yaml`
  - `agents/<agent-id>/.env`
  - `agents/<agent-id>/data/`
  - `data/`
  - `secrets/`
- Platform embedded Knowledge 配置归入 `platform.yaml`；默认部署不再读或写
  `config/knowledge.yaml`。
- 更新 install/init/docker/docs/tests/OpenSpec，删除旧 `config/*` 模板路径、root
  `.env.example` 不存在、`FLEETENT_HOME/agent.yaml`、`knowledge.yaml` 的矛盾要求。

## Capabilities

### Modified Capabilities

- `configuration`: canonical config/env examples live beside their runtime instances in
  Platform home and default Agent home; `config/` is not a deployment template namespace.
- `install-bootstrap`: install seeds explicit Platform home files and default Agent home
  files from root/agent-home examples.
- `platform-agent-lifecycle`: materialize writes Agent homes under `agents/<id>/`; Agent
  env stays Agent-scoped and does not receive Platform/KB construction secrets.
- `file-agent-runtime`: default Agent runtime path is `agents/default/agent.yaml`;
  legacy root `agent.yaml` single-file mode is removed for MVP.
- `knowledge-service-config`: embedded Knowledge construction config belongs to
  `platform.yaml` / Platform DB, not default `config/knowledge.yaml`.

## Module Boundary Impact

- **owning package**：`platform` owns Platform config loading/materialize; `runtime` owns Agent
  home loading; `intelligence` owns KB snapshot models but not Platform file paths.
- **public API surface**：新增/调整 Platform config loader public API（具体名称 implementation
  阶段确定）；调整 Knowledge config loader 从 path-bound `knowledge.yaml` 转为 snapshot-bound API。
- **owned tables**：无新增表；复用现有 Agent / model provider / KB connector / secret tables。
- **config namespace**：root Platform home: `.env`, `platform.yaml`; Agent homes:
  `agents/<id>/agent.yaml`, `agents/<id>/.env`; no canonical `config/` templates.
- **cross-module dependencies**：Knowledge operations consume a validated snapshot supplied by
  Platform DB/config; Agent runtime consumes only `agent.yaml` + Agent `.env`.
- **migration / shim plan**：MVP 未上线，不保留旧模板路径兼容。旧 loader 可在同一 change 中删除或降级为
  explicit-path helper，但默认路径不再指向 `config/knowledge.yaml` / `config/settings.yaml`。
