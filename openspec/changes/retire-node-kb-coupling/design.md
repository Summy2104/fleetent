# retire-node-kb-coupling — Design

## Context

kb-binding-provider-materialize（2026-07-05 落地）确立了 platform 物化为 managed agent 的 KB 接线权威：绑定 ∧ `Settings().kb_serve` 配置 → agent.yaml 产出 `provider: http`（`/search` 端点）+ key 经 desired-state secrets 下发。此前 D 波（agent-kb-http-provider）落的 node 侧兜底仍在：`reconcile._write_home` 在配置有绑定但 provider 非 http 时，读同机 `$FLEETENT_HOME/kb-service.yaml` 自行注入；容器后端则给每个 agent 容器 RO 挂 `tenants/<t>/kb/` 并在 spawn 前用 KB 嵌入式迁移垫底建库（服务容器内 local 直读形态）。

现状问题：a）双轨注入=两套口径，platform 侧演进（如本周 `/search` 端点修正）node 侧要跟改，否则行为分叉；b）fallback 掩盖配置错误——platform 未配 kb_serve 在单机被救活、多机才暴露；c）RO 挂载带 WAL 滞后快照隐患（agent 可能读到落后的 KB 快照，2026-07-02 已记录在案）。

## Goals / Non-Goals

**Goals:**

- managed agent 的 knowledge 接线只有一个来源：platform 物化产物。node 不读、不写、不补任何 knowledge 配置。
- agent 容器的文件面与 KB 彻底隔离（不挂载、不垫底），node 对 `knowledge_base` 包的 import 清零。
- 配置缺失 fail fast：platform 未配 kb_serve → 绑定不产生可用检索，管理面可见（而非被兜底掩盖）。

**Non-Goals:**

- 不动 standalone dev 形态：`fleetent agent run` 同机 local provider（agent_app 直读 + tenant_scope 注入）原样保留。
- 不动 platform 物化通路与 kb-serve/kb-worker 本身。
- 不做"绑定但未配置 kb_serve"的管理面告警（可后续单独加，属 UI/观测增强）。

## Decisions

**D1 — fallback 直接删除，不留开关。**
替代方案：feature flag 渐退——多一套要维护的分支，且保留期间掩盖效应依旧；真实部署面小（prod-1 + dev），升级说明足够。删净。

**D2 — 容器 KB 挂载与垫底一并删除，而非只删垫底。**
挂载失去消费者（managed 一律 http，容器内无 local 读）后留着只剩 WAL 隐患与攻击面。`ensure_tenant_kb_dir` / `KB_MIGRATIONS` / `create_substrate` 等 import 随删；租户 KB 目录的建立回归其正主（kb-serve/worker 的 migrate-on-open 与 router lazy-create）。

**D3 — 删除的验收用"守卫测试"表达（TDD 红绿仍成立）。**
先写新行为守卫（`_write_home` 对含绑定、provider 为 local 的配置**原样落盘**、不产生 knowledge secrets；ContainerBackend.spawn 的 docker run 参数**不含** KB 目录 mount），先红——旧代码会注入/挂载导致守卫失败——再删代码见绿。防止未来有人把 fallback 加回来。

**D4 — spec 语义收敛为"platform 物化唯一权威"。**
agent-knowledge-config 的 provider 默认段全文改写：managed http 由 platform 物化产出；node MUST NOT 注入；未配置 kb_serve 时保持 local 且明示"local 仅在与 KB 同机的 standalone dev 有效"。tenant-scoped-db-routing 删 agent 容器挂载条款，`kb/data/` 归组、单元搬迁、`.env` 隔离语义不动。

## Risks / Trade-offs

- **[存量 fallback 部署断 KB]** → 升级说明 + platform.yaml 模板已含 `kb_serve` 段；断的表现是"检索空结果 + agent 日志 http_knowledge_provider 未配置"，可诊断。
- **[单机 dev 少了一条自动接通路径]** → `make dev` 栈已注入 `KB_SERVE__*`（本周落地），dev 体验不回退。
- **[误删波及非 KB 挂载]** → 守卫测试同时断言 home 卷挂载仍在，只有 KB mount 消失。

## Migration Plan

无 DB 迁移。部署顺序无约束（node 先/后升级均安全：新 node 不再注入，旧 agent.yaml 中已物化的 http provider 不受影响）。回滚 = 回退 node 版本。

## Open Questions

- "有绑定但 platform 未配 kb_serve"是否值得在 admin UI/observation 上浮一个警示——留给 KB 观测面后续批次。
