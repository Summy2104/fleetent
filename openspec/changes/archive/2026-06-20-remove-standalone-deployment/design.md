## Context

现状:node 已是 agent 唯一 launcher(`retire-inmemory-controller` 后),platform 无直接拉 agent。standalone 的"代码能力"(`fleetent agent run` 无 platform 跑)源于解耦契约——agent 运行时本就不调 platform。所以"砍 standalone 部署"主要是**退役一个部署模式 + 改文档/install/规则措辞**,不是删 agent-run 代码。standalone 经 grep 确认无 tests/脚本硬依赖、仅文档引用。

## Goals / Non-Goals

**Goals:** 退役 standalone **部署模式**;reframe agent run/init 为 node 原语+dev;install-agent.sh 改 agent-host(node);单机 managed 路径成文;AGENTS.md 规则措辞改。

**Non-Goals:** 不删 `fleetent agent run`/`agent init`(node 用、dev 用);不碰 agent→platform 解耦契约与护栏;不碰 materialize/desired-state;不引入新代码能力。

## Decisions

### D1:解耦契约 vs standalone 部署——只动后者

AGENTS.md 那条规则当前混了两件事:① "agent 必须能无 platform 运行"(standalone 部署保证)② "依赖方向单向不可逆"(解耦契约)。**②保留原样**(永久铁律、护栏强制);**①改写**为"部署上 platform 始终在场;`fleetent agent run` 是 node 拉起原语+dev/test,非 standalone 部署模式"。关键:解耦契约不依赖 standalone 部署存在——agent 不 import platform 是代码事实,与"部署里有没有 platform"无关。

### D2:agent run/init 命令保留,只 reframe

node/backend.py 用 subprocess 调 `fleetent agent run`;dev 也直接用。命令**不删**。改的是 agent-runtime-cli spec 的**叙述**:从"standalone runtime / self-contained 部署"→"node 拉起原语 + dev/test 便利"。功能行为零变化。

### D3:install-agent.sh repurpose 为 agent-host installer

现状 install-agent.sh = "standalone agent installer(no platform)"。改为 = "agent host installer":装 runtime + node、配 node 接入 platform(`$FLEETENT_HOME/node/.env`),引导用 node 而非手 scaffold 无 platform agent。`agent init`/`agent run` 在教程里降级为"dev/调试"用法。

### D4:单机 managed 拓扑成文

deployment spec 加:单机 = platform+node+agent 同机,node 经 localhost desired-state 拉起 agent;与分布式机制一致、只差 co-location(对齐 §12 不变量)。

## Risks / Trade-offs

- **[误删 agent-run 能力]** 本 change **不删** agent run/init,只 reframe。design 明确:standalone 部署退役 ≠ 删 agent-run 代码。
- **[install-agent.sh 改动面]** 它的 spec(install-agent-script)+ 安装测试要同步;agent host 现在需 node 配置(`node/.env`)——install 引导补上。
- **[规则措辞超前]** 本 change 真落地时才改 AGENTS.md 那条(之前 roadmap 注明"规则随代码改")——本 change 就是那个"代码改",所以现在改措辞正当。
- **[文档广面]** standalone 在多份 capabilities/glossary 出现;逐处改为"已退役部署模式 / dev 用法",别漏。
