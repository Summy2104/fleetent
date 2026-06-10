## Context

3d 合拢 #3：前序切片把各库 router 化但"单主体 default 先"；本切片打开多主体 + 落 §7 只读投影。物理布局/命名见 data-model §5.7（17 库示例）；投影模型见 target-arch §7。

## Goals / Non-Goals

**Goals:** 多主体 fan-out（按 agent 归属主体路由 + provisioning）；platform 只读投影实现（只读 router + 共享读函数 + registry 遍历）。
**Non-Goals:** 跨主体共享 KB（主体内 M:N 已足）；PG/RLS 后端实现（可换后端另行）；新建任何物化副本。

## Decisions

**D1 路由主体来源 = agent 归属主体（`AgentContextIdentity.tenant_id`），非请求者 Principal。** 物理库按"哪个 agent 在跑"路由（§6.3/§6.4）；edge 另校验 `Principal.tenant_id == agent 主体`（#4）。
- 备选：按请求者 Principal.tenant 路由。否决——agent 服务多主体的人，库归 agent 主体；请求者 tenant 只做访问校验。

**D2 provisioning 归 platform agent_lifecycle（或 lazy 建目录）。** onboard 主体/agent 时建 `<tenant>/<agent_id>/`；router 开库时目录不存在则建（lazy 亦可）。

**D3 platform 只读投影 = 只读 router + 共享读函数 + registry 遍历（§7 模型落地）。** 不物化、不让 agent 反向写。读 stopped agent 历史靠直接读文件（WAL 下与写并发安全）。
- 备选：agent 出 API / 物化副本。否决（§7 已论：耦合可用性 / = session_meta 反例）。

**D4 聚合 = registry 遍历逐个只读开。** fleetent 个位数主体规模够用；热路径统计仍读 append-only trace。approvals 投影 join 身份（#4 解析不透明 actor）。

## Risks / Trade-offs

- **多主体路径漏改、误落 default。** → 护栏：解析非 default 主体时路径含主体段；跨主体读写隔离测试（agent 够不到别主体）。
- **provisioning 与 agent 启动竞态。** → 目录 lazy 建（开库即建父目录）+ 幂等。
- **只读投影的 schema 读耦合（§7.4）。** → 单体同仓经共享读函数、随 schema 同改；分布式未来换 PG 只读连接。
- **approvals 身份富化依赖 #4。** → #4 未落则投影显示不透明 actor；不阻塞读。

## Migration Plan

1. router 去 default 硬编码、按 `AgentContextIdentity.tenant_id` fan-out；provisioning 建目录。
2. router 加只读模式；platform 读侧（console/统计）改走只读 router + 共享读函数 + registry 遍历。
3. 跨主体隔离 + 只读投影端到端测试；上线前 fresh build per-主体结构。回滚 = revert（未上线、无数据）。

## Open Questions

- provisioning 触发点（agent_lifecycle materialize 时 vs router lazy 建）——倾向 router lazy 建父目录（最少协调），materialize 负责注册；apply 时定。
