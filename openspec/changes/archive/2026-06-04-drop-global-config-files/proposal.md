## Why

`single-agent-config-file` + `installer-seed-agent-yaml`（均已合并 main）确立了部署 agent 自包含、扁平 home（`agent.yaml` + `.env` + `data/`，无 `config/`）。全局配置文件 `config/settings.yaml` / `mcp.yaml` / `mcp.servers.yaml` 不再被 install 部署，且各加载器**已容忍其缺失→回退默认值**。但仓库仍保留这三个 `.example` 模板，且 `fleetent admin init-config` 仍 seed `settings.yaml`/`mcp.servers.yaml`——与新模型不一致、易误导 operator。本 change 清理这些孤立的全局配置模板与 seed 路径。

## What Changes

- 删除 `config/settings.yaml.example`、`config/mcp.yaml.example`、`config/mcp.servers.yaml.example`。
- `admin_cli/init_config.py`：从 `_GENERATED_FILES` 移除 `settings.yaml` 与 `mcp.servers.yaml` 两项（保留 `.env`）；更新提示文案。
- `Dockerfile`：`COPY config/*.yaml.example` 改为显式 `COPY config/agent.yaml.example`（语义明确，不依赖 glob 恰好命中）。
- **保留加载器**（`Settings` yaml source、`load_mcp_server_settings`、server lifespan mcp.yaml 块、sandbox config）——它们已容忍文件缺失，缺失即默认。**不删加载器、不收缩 `Settings`**：`settings.yaml` 当前还托管 `sandbox:` 段与 intelligence（KB/memory/vector/embedding/long_term_ctx）配置，二者的 → agent.yaml 迁移是显式 deferred 工作；现在删加载器会 strand 它们。

## Capabilities

### Added Capabilities
- `configuration`: 新增「全局配置文件可选」契约——agent 运行时不要求 `settings.yaml`/`mcp.yaml`/`mcp.servers.yaml` 存在；缺失时各子系统回退到内置默认值。

### Modified Capabilities
<!-- 无:init-config/Docker 的调整是实现细节,deployment 的行为要求未变(仍 seed .env、建 data 目录)。 -->

## Impact

- **删除**：3 个 `config/*.yaml.example`（全局）。
- **修改**：`admin_cli/init_config.py`、`Dockerfile`、`tests/unit/test_admin_init_config.py`、`tests/integration/test_deployment_docs.py`（断言已删模板处）。
- **依赖**：`installer-seed-agent-yaml`（已合并；提供 `config/agent.yaml.example` + 扁平 home seed）。
- **保留不动**：所有加载器（容忍缺失）、`Settings` 全字段、sandbox/intelligence（deferred）。
- **分支**：基于并合回 `main`。
