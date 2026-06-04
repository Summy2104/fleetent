## Why

`install.sh` 部署一个 agent 时，只把全局 `config/*.yaml.example` 拷进 `$FLEETENT_HOME/config/`，**从不 seed agent 自己的 `agent.yaml`**。配合 change `single-agent-config-file`（agent 运行时从 `FLEETENT_HOME/agent.yaml` 加载单体自包含 agent），缺了这一步 → 部署出的 agent 没有自己的配置文件，运行时回退到空/默认（用户实测：重构的 agent.yaml 不生效）。本 change 修复部署布局：install.sh seed `agent.yaml` 到 agent home 根目录，且部署目录**扁平、无 `config/`**。

## What Changes

- 新增 `config/agent.yaml.example`：单体 agent 的根目录模板（核心字段：system_prompt/model_overrides/skills/allowed_tools/plugins/features/mcp_servers/connectors/bindings；敏感值 `*_env` 引用；不含 KB/intelligence——后续）。
- `install.sh copy_config_templates` 重写为部署扁平布局：
  - seed `$FLEETENT_HOME/.env`（保留，存在即跳过）
  - seed `$FLEETENT_HOME/agent.yaml`（从 `config/agent.yaml.example`，存在即跳过）
  - **不再创建 `config/` 子目录、不再拷贝全局 `config/*.yaml.example`**（部署 agent 扁平：`agent.yaml` + `.env` + `data/`；settings/mcp/mcp.servers 缺失时各加载器回退默认）
- `--skip-config` 语义不变（跳过模板拷贝）。

## Capabilities

### Modified Capabilities
- `install-bootstrap`: 修改「配置模板」要求——部署 agent home 为扁平布局，install.sh seed 根目录 `agent.yaml`（自包含单体 agent 的配置），不再 seed `config/` 下的全局文件。

## Impact

- **新增**：`config/agent.yaml.example`。
- **修改**：`scripts/install.sh`（`copy_config_templates`）、`tests/integration/test_install_script.py`。
- **依赖**：`single-agent-config-file`（已合并 main，提供 `paths.agent_file()` + 单文件加载）。
- **不在本次**：删除全局 `*.yaml.example`、Dockerfile/`init_config` 的全局文件清理 → 由后续 `drop-global-config-files` 处理（避免删模板与 install 拷贝模板的破窗中间态；本 change 只让 install 停止拷贝全局文件并改 seed agent.yaml）。
- **不受影响**：加载器（settings/mcp/mcp.servers 仍容忍缺失→默认）、平台、Docker（本 change 不动 Dockerfile）。
- **分支**：基于并合回 `main`。
