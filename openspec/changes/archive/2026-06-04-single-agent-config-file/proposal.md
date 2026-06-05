## Why

部署出去的 fleetent agent 是**解耦的单体运行时**：它应当只读自己根目录下的一个 `agent.yaml`（自包含），数据全在本地，不依赖平台、不扫描多 agent 目录。但当前 `agent_config` 只支持多 agent 模式——扫描 `config/agents/<name>/agent.yaml` 并构建路由索引。这导致 `install.sh` 部署的单 agent 配置（应在 agent home 根目录）根本不被加载，运行时回退到默认/空 agent（用户实测：重构的 agent.yaml 没生效）。

本 change 给 agent 运行时增加**单文件 agent home 加载**：当 `FLEETENT_HOME/agent.yaml` 存在时，把它当作「唯一且默认」的 agent 加载；不存在时回退到既有的 `config/agents/` 多扫描（保留给 dev / 平台 / 向后兼容）。**不改动、不移除多 agent 机制**——多 agent 归平台控制面，本 change 只点亮单体 agent 运行时的自包含加载路径。

## What Changes

- `paths.py` 新增 `agent_file()` 解析器：`base_dir() / "agent.yaml"`（agent home 根，非 `config/`）。
- `agent_config.build_index()` 增加**单文件优先分支**：若 `agent_file()` 存在，加载该单一 `agent.yaml` 为唯一 agent，并强制其为 `default`（自包含单 agent 即默认，无需 `bindings.default: true`）；其 `bindings.channels`/`users` 仍进入路由表用于过滤。否则回退既有多扫描。
- 新增单文件加载函数：复用 `AgentFile` schema 与 `_reject_inline_secrets`，但**跳过「目录名必须等于 name」校验**（根目录 agent.yaml 无 `<name>/` 父目录）。
- 所有 `agent_config.current()` 消费者（normalizer 路由、snapshot、slack_supervisor、server）**无需改动**——它们读索引，单文件模式下索引含一个默认 agent。

## Capabilities

### Modified Capabilities
- `file-agent-runtime`: 新增「单文件 agent home 加载」语义——`FLEETENT_HOME/agent.yaml` 存在时作为唯一且默认 agent 加载（优先于多扫描），跳过目录名校验；多扫描行为在单文件不存在时保持不变。

## Impact

- **修改代码**：`src/fleetent/paths.py`（加 `agent_file()`）、`src/fleetent/agent_config.py`（单文件分支 + 单文件 loader）。
- **不改**：normalizer / snapshot / slack_supervisor / server（通过 `current()` 间接受益）；`AgentFile` schema 维持现核心字段（KB/memory/intelligence 不在本次）。
- **依赖关系**：本 change 是 `drop-global-config-files`、`installer-seed-agent-yaml` 的前置（确立 `agent_file()` 路径契约）。
- **不受影响**：多 agent 扫描、平台控制面、DB authoring。
- **分支**：基于并合回 `main`。
