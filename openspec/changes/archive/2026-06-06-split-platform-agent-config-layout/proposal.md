## Why

Fleetent 的配置文件已经经历了多轮演进，当前仓库里同时存在 `config/agent/agent.yaml.example`、
`config/agent/.env.example`、`config/platform/.env.example`、`config/knowledge.yaml.example`、
`config/agents/*/agent.yaml.example` 与 tracked `config/agent.yaml`。这些路径混合了模板、真实本地
配置、dev multi-agent scan 示例、平台配置和 Agent runtime 产物，导致 operator 与实现者无法一眼判断：

- 哪个模板是 canonical。
- `.env` 到底属于平台进程还是 Agent runtime。
- knowledge/memory 默认是否已经是独立服务。
- 平台部署 Agent 时应该从哪里派生 `agent.yaml + .env`。

MVP 未上线，不需要保留这些历史路径。应先把配置组织收敛到两个视角：Platform 与 Agent。Knowledge、
memory、worker 等能力默认仍归 Platform side；未来独立服务化时再从 Platform side 拆出自己的 service
home，而不是现在就把默认部署拆碎。

## What Changes

- 定义 Platform / Agent 两类配置边界：
  - **Platform side**：平台进程配置与 env、平台 DB、Agent authoring、部署/materialize、默认内嵌的
    knowledge / memory / worker 能力。
  - **Agent side**：某个 Agent runtime 的 `agent.yaml`、`.env`、`data/`；runtime 自包含，不读平台 DB。
- 平台管理和部署 Agent 时， SHALL 从平台 DB + Platform 配置派生 Agent home：
  `agents/<agent-id>/{agent.yaml,.env,data/}`。
- 默认部署不再把 `knowledge.yaml` 作为必须存在的独立文件；knowledge 跟平台一起部署时归入 Platform
  config/env。只有独立 Knowledge Service 部署时，才使用独立 `knowledge.yaml + .env`。
- 清理仓库模板语义：
  - Platform 模板只表达平台进程与默认内嵌服务配置。
  - Agent 模板只表达 Agent runtime 文件形状。
  - dev multi-agent scan 示例移出 canonical config 模板路径，作为 examples / fixtures。
  - tracked `config/agent.yaml` 不再作为 canonical 配置样例。

## Capabilities

### Modified Capabilities

- `configuration`: 收敛配置模板布局与 Platform / Agent env 边界。
- `install-bootstrap`: 安装/初始化只 seed Platform 或默认 Agent home 对应文件，不再依赖混杂模板路径。
- `platform-agent-lifecycle`: 平台 materialize Agent home 的目标布局固定为 Agent side。
- `knowledge-service-config`: 默认平台内嵌 knowledge 不要求独立 `knowledge.yaml`；独立服务部署时才启用。

## Module Boundary Impact

- **owning package**：`platform` owns Platform config/env authoring 与 Agent home materialize；`runtime`
  owns Agent home loading；`intelligence` owns knowledge/memory runtime semantics but default config belongs
  to Platform side until split into services.
- **public API surface**：无新增 runtime public API；materialize 目标路径契约会在
  `platform.agent_lifecycle` 内明确。
- **owned tables**：无。
- **config namespace**：新增明确的 Platform side 与 Agent side 命名边界；default knowledge config moves
  under Platform config when embedded.
- **cross-module dependencies**：Platform materialize 仍依赖 AgentFile schema；Agent runtime 不依赖 Platform
  DB 或 Platform config。
- **migration / shim plan**：MVP 未上线，无兼容 shim。旧模板路径和 tracked 本地配置直接迁移/删除，测试和
  文档随之更新。

## Impact

- **配置模板**：重组 `config/` 下的 platform / agent 模板，移除或迁移 confusing examples。
- **文档/spec**：更新 README、deployment docs、`openspec/specs/configuration`、`install-bootstrap`、
  `platform-agent-lifecycle`、`knowledge-service-config` 中的旧路径。
- **代码/脚本**：后续 implementation 会同步 install/init/materialize 的模板源路径和目标路径。
- **不做**：不实现独立 Knowledge Service，不设计完整 service registry，不修改 credential authoring 的
  secret store/API。
