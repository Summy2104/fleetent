## Context

`single-agent-config-file`（已合并）让 agent 运行时从 `paths.agent_file()`=`base_dir()/agent.yaml` 加载单体自包含 agent。但 `install.sh` 的 `copy_config_templates` 仍是旧逻辑：建 `$FLEETENT_HOME/config/`，拷贝 `config/*.yaml.example`（settings/mcp/mcp.servers）到那，**不 seed agent.yaml**。结果部署的 agent 没有 home-root agent.yaml，运行时回退默认。

加载器现状（已验证）：settings.yaml / mcp.yaml / mcp.servers.yaml 的读取方均容忍缺失→默认值。故部署 agent 无这些全局文件可正常跑。

## Goals / Non-Goals

**Goals:**
- install.sh seed `$FLEETENT_HOME/agent.yaml`，部署 home 扁平（`agent.yaml` + `.env` + `data/`，无 `config/`）。
- 提供 `config/agent.yaml.example` 作为单体 agent 根模板。
- 幂等（存在即跳过）、`--skip-config` 保留。

**Non-Goals:**
- 不删全局 `*.yaml.example`、不动 Dockerfile / `init_config`（→ `drop-global-config-files`）。
- 不引入 KB/intelligence 到模板（后续）。
- 不动加载器 / Settings。

## Decisions

**D1：部署 home 扁平，无 config/。**
`install.sh` 不再 `mkdir config` / 拷贝 `config/*.yaml.example`。只 seed `agent.yaml` + `.env` 到 home 根。与 `paths.agent_file()`=`base_dir()/agent.yaml` 契约一致；全局文件缺失由各加载器回退默认覆盖。

**D2：`config/agent.yaml.example` 为单体根模板。**
基于既有 `config/agents/example/agent.yaml.example`，但头注释改为「单体 agent home 根 `agent.yaml`」语义（非 `config/agents/<name>/`），保留核心字段，去掉「目录名必须等于 name」的说明（单文件模式跳过该校验）。不含 KB/intelligence 段（后续）。

**D3：本 change 让 install 停止拷贝全局文件，但不删模板本身。**
删除 `config/*.yaml.example` 会让仍引用它们的 Dockerfile（`COPY config/*.yaml.example`）与 `init_config` 破窗。故顺序上 install 先停拷贝（本 change），模板删除 + Dockerfile/init_config 清理留给 `drop-global-config-files`，避免中间态破坏构建。

## Risks / Trade-offs

- **[已部署用户已有 config/ 布局]** → 旧部署仍可用（加载器读 config/ 下文件或回退）；新部署走扁平。`agent.yaml` 存在即跳过，重跑安全。
- **[install 测试依赖旧拷贝行为]** → 更新 `test_install_script.py`：断言 seed `agent.yaml`（根）、不再断言 `config/settings.yaml` 等。
- **[模板与运行时 schema 漂移]** → `config/agent.yaml.example` 字段对齐 `AgentFile` 核心字段；新增测试可加载该模板（`load_agent_home_file` 不报错）。

## Migration Plan

纯部署脚本 + 新模板，无运行时代码改动。回滚 = 还原 install.sh + 删 `config/agent.yaml.example`。
