## Context

`agent_config.py` 是 file-driven 多 agent 加载器：`build_index` 扫描 `<agents_dir>/<name>/agent.yaml`，构建 `{agents, by_channel, by_user, default}` 路由索引；`AGENTS_DIR = paths.config_dir()/"agents"`，可经 `FLEETENT_AGENTS_DIR` 覆盖。消费者（`server.scan()`、`normalizer.current()`、`snapshot`、`slack_supervisor`、`runtime/loop`）都读 `current()` 索引。

部署的 agent 运行时是单体自包含的（见 brainstorming 设计 `docs/superpowers/specs/2026-06-04-agent-config-self-contained-design.md`）：agent home 根目录放一个 `agent.yaml`，无 `config/` 子目录。当前加载器看不到它。

## Goals / Non-Goals

**Goals:**
- agent 运行时能从 `FLEETENT_HOME/agent.yaml` 加载单一自包含 agent。
- 复用现有 `AgentFile` schema、密钥拒绝、index 数据结构与全部消费者（零下游改动）。
- 不破坏既有多扫描（dev / 平台 / 向后兼容）。

**Non-Goals:**
- 不移除/简化多 agent 路由、绑定、per-agent Slack（多 agent 归平台，另案）。
- 不扩展 schema 引入 KB/memory/intelligence（后续单独 change）。
- 不动 `settings.yaml`/`mcp.yaml`（属 change 2）、不改 install.sh（属 change 3）。

## Decisions

**D1：单文件优先，多扫描回退。**
`build_index` 先看 `paths.agent_file()`（=`base_dir()/agent.yaml`）：存在则只加载这一个 agent；否则走既有 `config/agents/` 扫描。理由：部署单体 agent 自包含在 home 根；dev/平台仍可用多扫描。二者互斥、零歧义。
- 备选：环境变量切换模式。弃因：文件存在性即是最自然的信号，少一个配置项。

**D2：单文件 agent 强制为 default。**
自包含单 agent 即「这个部署的 agent」——它必须能响应一切路由，故在单文件分支强制 `default = agent.name`，无论 `bindings.default`。其 `bindings.channels`/`users` 仍填入 `by_channel`/`by_user`（用于 connector/过滤语义，不改）。
- 备选：要求文件里写 `bindings.default: true`。弃因：单体部署下这是冗余样板，易漏写导致路由落空（正是用户踩的坑的一种）。

**D3：单文件 loader 跳过「目录名 == name」校验。**
根目录 `agent.yaml` 没有 `<name>/` 父目录，原校验不适用。新增 `load_agent_home_file(path)`：复用 `AgentFile.model_validate` + `_reject_inline_secrets`，不做目录名校验。多扫描路径的 `load_agent_file(agent_dir)` 保持原校验不变。

**D4：`paths.agent_file()` 在 home 根，不在 config/。**
`agent_file() = base_dir()/"agent.yaml"`。与部署布局（扁平、无 config/）一致。`config_dir()` 仍保留（多扫描的 `config/agents/` 与 change 2 前的全局文件仍用），本 change 不动它。

## Risks / Trade-offs

- **[单文件与多扫描同时存在]** → 二者按 D1 互斥（单文件优先），不会叠加；在 home 根有 agent.yaml 时多扫描被完全跳过，行为确定。
- **[强制 default 改变路由直觉]** → 仅在单文件模式生效；多扫描模式 default 仍由 `bindings.default` 决定，回归保护测试锁定。
- **[消费者假设可能依赖多 agent]** → 经审查，消费者只读 `current()` 索引（get/by_channel/by_user/default/slack_agents），单文件模式下索引含一个默认 agent，全部正常工作；新增测试覆盖单文件索引被各消费点正确读取。

## Migration Plan

纯新增加载路径，默认行为（无 home 根 agent.yaml 时）不变。回滚 = 还原 build_index 的单文件分支与 `agent_file()`。
