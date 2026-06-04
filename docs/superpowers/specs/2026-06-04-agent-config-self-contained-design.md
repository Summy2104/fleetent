# Self-contained single-agent config — design & decisions

**日期**: 2026-06-04 · **负责人**: 张洋（自主执行授权 by Claude）· **状态**: 实施中

## 背景与目标

fleetent 是两层架构：

- **平台 = 多 agent 控制面**：authoring（DB）、管理控制台、**生成并下发 agent.yaml**。本次重构**不动平台**。
- **agent = 解耦的单体运行时**：每个部署的 agent 只读自己的 `agent.yaml` + `.env`，数据（users/sessions/traces/logs）全在本地 `FLEETENT_HOME/data/`，不依赖平台、不读全局配置文件。

起因：用户实测 `install.sh` 部署后，重构的 agent.yaml 未生效——根因是 agent 运行时只支持 `config/agents/<name>/` 多扫描，看不到部署在 home 根的单文件，且 `install.sh` 也没 seed agent 配置。

## 部署布局（install.sh 产出，扁平、无 config/）

```
<agent-home = FLEETENT_HOME>/
  agent.yaml      # agent 配置，直接在根目录（路径 = base_dir()/agent.yaml）
  .env            # 敏感值，变量映射（*_env / env:VAR，不内联）
  data/           # 本地数据：fleetent.db / sessions/ / traces.jsonl / logs/
```

## 本次范围（仅核心能力）

agent.yaml 自包含 agent 核心能力：`system_prompt` / `model_overrides` / `skills_dir` / `allowed_skills` / `allowed_tools` / `plugins` / `features` / `mcp_servers`（`*_env` 引用）/ `connectors` / `bindings`。

**本次不做（后续单独 change）**：KB、memory、vector_store、embedding、rerank、long_term_ctx —— 先跑各自默认值（等于关闭/默认）。agent.yaml「手写源 vs DB 生成」关系也暂不纠结（运行时只管读）。

## 三个 change（顺序 1 → 2 → 3）

| # | change | 内容 |
|---|---|---|
| 1 | `single-agent-config-file` | `paths.agent_file()` + `agent_config` 单文件 home 加载（唯一且强制 default），优先于多扫描；消费者零改动 |
| 2 | `drop-global-config-files` | 删 `settings.yaml`/`mcp.yaml`/`mcp.servers.yaml`（含 `.example`）；`Settings` 收缩为本地 infra（db/logging，paths 默认 + .env）；deferred intelligence 跑默认 |
| 3 | `installer-seed-agent-yaml` | `install.sh` seed `$FLEETENT_HOME/agent.yaml`（根，不建 config/），修最初的 bug |

## 决策日志（Decisions）

- **D1（change1）单文件优先、多扫描回退**：`build_index` 在 `agents_dir is None` 且未设 `FLEETENT_AGENTS_DIR` 且 `paths.agent_file()` 存在时，加载单文件；否则多扫描。显式 `FLEETENT_AGENTS_DIR`/`agents_dir` 永远走多扫描（保护既有测试与平台用法）。
- **D2（change1）单文件 agent 强制 default**：自包含单 agent 必须能响应一切路由，故 `default = agent.name`，无视 `bindings.default`（避免漏写样板导致路由落空——正是用户踩的坑之一）。
- **D3（change1）单文件 loader 跳过目录名校验**：`load_agent_home_file` 复用 `AgentFile` 校验 + 拒绝内联密钥，但不做「目录名==name」校验（根文件无 `<name>/` 父目录）。
- **D4（change1）`AGENTS_DIR` 常量保持不变**（一个测试断言它 == `config_dir()/agents`）；单文件路径用 `paths.agent_file()`（live）。

## 问题日志（Issues encountered）

- **I1（关键发现）加载器均容忍文件缺失**：`settings.yaml`（Settings yaml source，现成测试 `test_settings_missing_yaml_file_uses_typed_defaults` 证明）、`mcp.yaml`（server lifespan existence-guarded）、`mcp.servers.yaml`（`load_mcp_server_settings` 缺失返回 `[]`）、sandbox config/enablement（缺失返回默认）。⇒ 部署 agent 无这些全局文件即跑默认，本就可用。
- **I2 settings.yaml 仍托管 sandbox + intelligence 配置**：`integrations/sandbox/{config,enablement}.py` 读 `settings.yaml` 的 `sandbox:` 段；intelligence 也在 `Settings`。⇒ **决策：推迟「删加载器 + 收缩 Settings」**，与 sandbox/intelligence→agent.yaml 迁移一起（deferred）。change 2 只删被 seed 的全局模板，不动加载器。
- **I3 .example 与 install/Docker/init_config 的 seed 路径耦合**：删全局 `.example` 会让 install.sh / `Dockerfile(COPY config/*.yaml.example)` / `init_config` 破窗。⇒ **决策：重排 1→3→2**。change 3 先改 install seed `agent.yaml`（扁平 home）、停拷全局文件；change 2 再删孤立模板 + 修 Dockerfile/init_config。
- **I4 部署 home 扁平无 config/**：install.sh seed `$FLEETENT_HOME/{agent.yaml,.env}` + `data/`。新增 `config/agent.yaml.example`（核心字段、无 intelligence）。

## 待审核要点（供张洋最终 review）

- 单文件「强制 default」语义是否符合预期（D2）。
- change 2 删 `settings.yaml` 后，deferred 的 KB/memory/vector 等跑默认值（关闭）是否可接受到「后续再做」之前。
- install.sh 扁平布局（无 config/）是否最终形态。
