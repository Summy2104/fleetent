## Context

当前实现已经有两个事实边界：

- Platform control plane 是 FastAPI 管理面，负责 authoring、console、provider、KB 管理、Agent lifecycle。
- Agent runtime 可以独立运行，读自己的 `agent.yaml + .env + data/`，不依赖平台服务。

配置治理应贴合这两个事实，而不是按模块名提前拆出多个配置文件。Knowledge、memory、vector、worker 未来
都可能服务化，但在默认 MVP 部署中它们仍是 Platform side 的内部能力。

## Goals / Non-Goals

**Goals:**

- 用 Platform / Agent 两个视角收敛配置和 env。
- 让平台部署 Agent 的产物明确为 self-contained Agent home。
- 让 knowledge 默认内嵌平台时不需要独立 `knowledge.yaml`；独立部署时保留可扩展路径。
- 消除 `config/agent/` vs `config/agents/`、tracked `config/agent.yaml`、旧
  `config/agent.yaml.example` 等歧义。
- 与 `agent-credential-authoring` 对齐：平台主密钥属于 Platform ENV，Agent `.env` 由 materialize 产生。

**Non-Goals:**

- 不设计完整 `platform.yaml` 字段集合。
- 不实现 Knowledge / Memory / Worker / Model Gateway 独立服务。
- 不改变 AgentFile 业务 schema。
- 不改变 credential slot / secret store / write-only API 的设计。

## Decisions

### D1 — 两类一等配置边界

配置按归属视角分两类：

```text
Platform side
  platform config
  platform env
  platform DB
  Agent authoring / deployment / materialize
  embedded knowledge / memory / worker defaults

Agent side
  agent.yaml
  .env
  data/
```

Platform 是 source of truth；Agent 文件是部署产物。Agent runtime 不读 Platform DB、不读 Platform config。

### D2 — Agent home 是 materialize 产物

平台部署 Agent 时写入：

```text
<fleetent-home>/agents/<agent-id>/
  agent.yaml
  .env
  data/
```

`agent.yaml` 只含非敏感结构化配置与 `*_env` 引用；`.env` 含该 Agent 运行所需的 env 值或空占位；
`data/` 是该 Agent runtime 的本地状态。

单 Agent 快速安装可以创建一个默认 Agent home，但不再把 Platform home 根目录本身当成 Agent home。

### D3 — Platform env 与 Agent env 不混

Platform ENV 包含平台进程变量：`FLEETENT_SECRET_KEY`、`DATABASE_URL`、平台日志、sandbox endpoint、
未来 remote service endpoint 等。

Agent ENV 包含该 Agent runtime 所需变量：model provider API key、Slack/IM token、MCP secret、KB connector
secret 等。Agent ENV 由 materialize / `fleetent agent init` 生成，平台进程变量不得写入 Agent home。

### D4 — Knowledge 默认属于 Platform side

默认部署中，knowledge / memory / vector / worker 配置属于 Platform config/env。不存在默认必需的
`config/knowledge.yaml`。

当 Knowledge Service 独立部署时，才引入独立 service home：

```text
<fleetent-home>/services/knowledge/
  knowledge.yaml
  .env
  data/
```

此时 Platform config 只保存连接方式和授权 env 引用，而不是内嵌索引/数据源构建细节。

### D5 — 仓库模板只表达 canonical 场景

仓库模板应与两个视角对应：

```text
config/
  platform/
    platform.yaml.example
    .env.example

  agent/
    agent.yaml.example
    .env.example
```

`config/platform/.env.example` 是 Platform ENV 模板；`config/agent/.env.example` 只表示 Agent runtime
env 文件形状，不承载 `FLEETENT_SECRET_KEY` 或平台 DB 变量。实际 Agent `.env` 仍由 materialize 根据具体
Agent required-env 生成。

dev multi-agent scan 示例不作为 canonical 配置模板，迁移到 `examples/agents/` 或测试 fixtures。

### D6 — multi-agent scan 是开发/运行能力，不是配置主线

现有 `config/agents/<name>/agent.yaml` scan 能力可以保留，用于开发、测试或手工多 Agent 本地运行。但
Platform 部署主线是 materialize 到 `agents/<agent-id>/` home。文档中不得把 `config/agents/example`
描述为部署模板。

## Risks / Trade-offs

- [需要改 install/runtime 路径] → MVP 未上线，不保留 shim；通过 OpenSpec 和测试一次性收敛。
- [agent 模板 `.env.example` 可能看起来为空] → 允许保留文件形状说明；真实 required env 由 materialize
  生成，避免静态模板与实际 Agent 配置漂移。
- [独立 Knowledge Service 暂不落地] → design 保留未来 service home，但默认仍内嵌平台，避免过早拆分。
- [与 agent-credential-authoring 并行] → 本 change 定义边界；credential change 在边界内实现 secret
  slot 与 materialize resolver。若同时执行，先改路径 contract，再执行 credential materialize 任务。

## Open Questions

无。已关闭：

- 默认只分 Platform / Agent 两个视角。
- Knowledge 默认归 Platform side，独立服务部署才有独立 config/env。
- Platform 主密钥属于 Platform ENV，不属于 Agent ENV。
- `config/agents/*` 不作为 canonical 部署模板。
