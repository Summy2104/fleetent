# 模块架构（核+4面+基座）—— 决策记录（rationale）

> 记录 fleetent 模块架构（一个核 + 四个面 + 共享基座）的**为什么**。现状/模型见 [`architecture/target-architecture-proposal.md`](../../architecture/target-architecture-proposal.md)；本文保留根因诊断、决策依据与"解决了什么"，供回溯。持久层/多租户/实体减法的 rationale 另见 [`persistence-redesign-decisions.md`](./persistence-redesign-decisions.md)。

## 根因诊断（重设计起因）
项目「怎么看怎么乱」的根因（依赖扫描 + 模块体量分析）：
1. **四种性质完全不同**的外围功能压进一个 `platform/` 命名空间 + 一堆顶层散文件；
2. 少数**巨型文件**（`loop.py` 2591 行、`reflection.py` 1747 行、`agent_store.py` 685 行…）一个文件干多件事；
3. 几个模块（`user_store`、`knowledge_base`、`governance`）**横跨本应分开的边界**。

包级职责切分**大体健康**——乱不在「切错架构」，而在「外围没结构」+「少数模块太胖/横跨边界」。核+4面+基座模型即收编这些。

## 架构决策
- **面的数量 = 4**（① 边缘 / ② 控制 / ③ 编排 / ④ 摄取，互不合并）：
  - **④ 摄取保持独立**（不并入②）：定义 vs 执行——② 是人同步定义配置、④ 是系统异步执行数据处理（解析/embedding/写入），运行特征/失败模式/扩容需求不同，且最可能将来独立扩容。
  - **② 控制 与 ③ 编排不合并**：③ 是 daemon/调度 character、独立可用性，与 ② 同步人工 CRUD 是两种东西。`materialize`(store 配置→agent.yaml) 是 **②→③ 转换桥**。
- **物理形态 = 单体**：四个面做成一等限界上下文、边界按「可拆服务」画；不现在拆微服务（多进程运维违背 lean/on-prem）。哪天某面（最可能 ④ 摄取）需独立扩容，能整面抽出。
- **依赖铁律**：面→核（允许）；核→面（禁，核须脱离任何面独立跑）；任意→基座（允许）；基座→业务（禁）；面↔面默认不互相 import、只经核/基座契约通信。
- **用户体系 = 内置模块 + `Identity` 端口**：authn 属 edge、核只消费 `Principal`、user 管理归 ②；agent 侧解析器不 import platform → 结构性根除 #1 泄漏。OIDC/Google 适配器后续。
- **governance 三拆 / reflection 两拆 / KB 四分**：能力本体/运行时执行→核；管理/审批/review API→②；审计/策略/建议数据→基座（核写、② 只读，不反向写 platform 表）。依据 CLAUDE.md「审批门≠归控制面」「自进化纵向元能力」。
- **platform 读侧投影**：platform 只读 agent 侧库（只读 router + 共享读函数 + registry），不物化副本、不让 agent 反向写。详见 target-arch §7。
- **resource_monitoring v1 整体外置** → Prometheus/Grafana（原拟入基座 observability，因是 Prometheus 生态弱重造而删）。

## 解决了哪些问题（速查）
| 原问题 | 在模型里如何消解 |
|---|---|
| 顶层「杂物抽屉」17 散文件 | 每个归入某面或基座 |
| `platform/` 一命名空间塞四种东西 | 拆①②③④四面 |
| `user_store` 三职责 + 泄漏#1 + 与 governance 真循环 | 沿面边界拆（§6）；authn 走 Identity 端口，#1 结构性消失 |
| `knowledge_base` retrieval/ingest 混 | 升级为核↔④面硬边界（KB 四分） |
| 巨型文件（loop/reflection/agent_store） | 核/面内部内聚拆分，正交、可独立做 |
| A/B 严格分层之争 | 退化为「面→核单向 + 全员→基座向下」——「核+外围」直觉的精确版 |

## 实现进度
持久层数据架构（§4 五库 / §6 Identity / §7 只读投影）+ 多租户物理隔离**已落地**（持久层 #1–#4，见 persistence-redesign-decisions）；模块边界重组（§3 四面 / §5 三拆·两拆·四分）**部分落地、持续推进**（KB 四分、Identity、向量整改已成）。
