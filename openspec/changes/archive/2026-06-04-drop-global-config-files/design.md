## Context

部署 agent 已扁平自包含（changes 1+3 合并）。全局 `config/{settings,mcp,mcp.servers}.yaml` 不再被 install 部署，加载器均容忍缺失→默认（已验证：Settings 有现成测试、sandbox config/enablement 缺失返回默认、mcp.servers 返回 []、mcp.yaml existence-guarded）。残留：3 个全局 `.example` 模板 + `init_config` 仍 seed 其中两个。

## Goals / Non-Goals

**Goals:**
- 删除 3 个全局 `.example`；`init_config` 不再 seed 它们；Dockerfile COPY 显式化。
- 用 spec 固化「全局配置文件可选，缺失→默认」契约。

**Non-Goals（显式 deferred，见决策）:**
- 不删加载器、不收缩 `Settings`：`settings.yaml` 还托管 `sandbox:` 段（`integrations/sandbox/{config,enablement}`）与 intelligence 配置；其 → agent.yaml 迁移是后续工作。
- 不动 Docker 单 agent 运行时布局（容器内 `/app/agent.yaml` 的放置）——后续。

## Decisions

**D1：只删模板 + seed 路径，保留加载器。**
加载器容忍缺失，删模板即让「全局文件不存在」成为常态、跑默认。删加载器/收缩 Settings 被 sandbox+intelligence 阻塞（deferred），故本 change 不碰。把「缺失→默认」写成 `configuration` 的 spec 契约，固化这一行为。

**D2：Dockerfile COPY 显式化。**
`COPY config/*.yaml.example` 在删除 3 个全局后仅剩 `agent.yaml.example` 命中，依赖 glob 偶然性脆弱。改 `COPY config/agent.yaml.example ./config/`，语义明确、构建稳定。

**D3：init_config 保留 `.env` seed，去掉两个全局文件。**
`fleetent admin init-config` 仍是 .env + 数据目录脚手架；去掉 settings.yaml/mcp.servers.yaml 两项与对应提示。不在此 seed agent.yaml（install.sh 负责部署 agent；init-config 是平台侧最小脚手架）。

## Risks / Trade-offs

- **[删 .example 破窗]** → 已核实：Dockerfile 改显式 COPY；init_config 去引用；tests 同步。无运行时加载器依赖 .example（它们读的是真实文件，缺失即默认）。
- **[operator 习惯 settings.yaml]** → `validate-config` 与文档仍可引用；本 change 不删加载器，operator 若手动放 settings.yaml 仍被读取（向后兼容）。
- **[保留加载器显得半成品]** → 在 design/审核要点显式记录这是 deferred（与 sandbox/intelligence 迁移一起），非遗漏。

## Migration Plan

删模板 + 改 init_config/Dockerfile + 测试同步。回滚 = 恢复 3 个 `.example` 与 init_config 条目。运行时无影响（加载器早已容忍缺失）。
