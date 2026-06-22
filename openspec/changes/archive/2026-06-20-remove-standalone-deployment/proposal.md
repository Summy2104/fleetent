## Why

target-architecture §12 定的部署不变量:**只两种拓扑——单机 / 分布式,platform 始终在场**;standalone(无 platform)部署模式退役(消冗余/一致性:避免"手写 agent 配置 vs platform materialize"两套路径)。现状已具备前提:`retire-inmemory-controller` 后 **node 是 agent 的唯一 launcher**,platform 侧无直接拉 agent 路径。本 change 把 standalone 从**受支持的部署模式**移除,并把 `fleetent agent run` / `agent init` 正名为 **node 拉起 agent 的原语 + dev/test 用途**(不再宣传为独立部署形态)。

**保留不变(重要)**:agent→platform **解耦契约**(agent MUST NOT import platform,护栏强制)——它正是让 node 把 agent 当独立进程管理的基础,且与"platform 始终在场"不矛盾(agent 运行时本就不调 platform)。`fleetent agent run` / `agent init` 命令**保留**(node 用、dev 用)。

## What Changes

- **改 AGENTS.md「不可逾越的规则」措辞**:把"agent 必须能在没有 platform 的环境下独立运行"改为——**部署上 platform 始终在场;agent 运行时不依赖 platform(解耦契约不变);`fleetent agent run` 是 node 的拉起原语 + dev/test,不是 standalone 部署模式**。解耦契约段(单向依赖)原样保留。
- **reframe `agent-runtime-cli` spec**:`agent run`/`agent init` 的描述从"standalone agent runtime / self-contained 部署"改为"node 拉起 agent 的原语(也可 dev 直跑)";命令行为不变。
- **repurpose `install-agent.sh`**:由"standalone agent runtime installer(no platform required)"改为"**agent host installer**":装 runtime + node,引导以 node 接入 platform(managed),而非 scaffold 无 platform 的 standalone agent。
- **单机 managed 路径成文**:单机 = platform + node + agent 同机;node 经 localhost 拉期望态、拉起 agent。补 `deployment` spec 的单机拓扑要求。
- **文档同步**:target-architecture(§12 已写,去掉"现状仍 standalone"的过渡注记)、capabilities/*、glossary 中把 standalone 描述为已退役部署模式。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `agent-runtime-cli`:`agent run`/`agent init` 由 standalone 部署形态 reframe 为 node 拉起原语 + dev/test(命令不变);移除"无 platform 独立部署"作为受支持模式的措辞。
- `deployment`:新增"只两种拓扑(单机/分布式),platform 始终在场;单机= platform+node+agent 同机,node 拉起 agent"。
- `install-agent-script`:`install-agent.sh` 由 standalone installer 改为 agent host(node)installer。

## Impact

**owning package**:`scripts/install-agent.sh`、文档、specs;**AGENTS.md**(不可逾越规则措辞)。代码面小——`fleetent agent run`/`agent init`/解耦护栏均不变。

**public API surface**:无 HTTP 变更;CLI 命令不变(语义 reframe)

**owned tables**:无　**config namespace**:无　**migration**:无

**BREAKING(部署文档级)**:不再支持"装一个 agent、不要 platform"的部署;agent host 改为跑 node 接入 platform。`fleetent agent run` 本身仍可被 dev 直接跑(不删)。

**边界铁律**:agent→platform 解耦护栏 `test_module_dependency_guardrails` 不变、仍绿——本 change 不碰解耦,只退役 standalone **部署模式**。

**已知风险**:确认无测试/脚本**硬依赖** standalone(已 grep:standalone 仅文档引用,无 tests/ 硬依赖);install-agent.sh 改动需同步其 spec 与安装测试。
