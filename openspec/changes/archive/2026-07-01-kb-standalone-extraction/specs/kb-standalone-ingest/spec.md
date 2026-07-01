## ADDED Requirements

### Requirement: 手动 extraction 命令

KB 服务 SHALL 提供命令式 extraction 入口 `fleetent kb extract`,对指定 KB **开启实体/关系抽取并回填存量文档**,**纯 KB 服务侧、不依赖 platform**。命令 SHALL 复用 `--config <kb-service.yaml>` 解析 tenant_id/队列/抽取模型配置。

- 命令 SHALL 置该 KB `extraction_enabled=true`(对存量 KB 亦可开启)。
- 回填 SHALL 经**入队**完成:遍历该 KB 存量文档,每文档入队一个 `extraction` job(与 ingest 侧 auto-enqueue 同形),由 kb-worker 作为**唯一消费者**抽取执行并写 `kb_entities`/`kb_entity_mentions`/`kb_relations`;命令 SHALL NOT 在自身进程内直写 kb.db。
- 入队前 SHALL 校验目标 KB 存在。`--wait` 时 SHALL 阻塞至完成并打印 documents/entities/relations 计数,超时提示检查 kb-worker。
- 抽取模型 SHALL 取自 `kb-service.yaml` 的 `extraction` 段(`kb_extraction` route);仓库 example SHALL 预置该段(默认 `enabled: false`,endpoint 指向自托管抽取模型),运维填模型并开启即用。

#### Scenario: 开启并回填存量文档
- **WHEN** 运维运行 `fleetent kb extract --config <kb-service.yaml> --kb <kb_id>`
- **THEN** 该 KB `extraction_enabled` 置真,其存量文档各入队一个 `extraction` job
- **AND** kb-worker 抽取执行,写 `kb_entities`/`kb_entity_mentions`/`kb_relations`,全程不依赖 platform

#### Scenario: 目标 KB 不存在
- **WHEN** `--kb` 指向本租户 kb.db 不存在的 KB
- **THEN** 命令报清晰错误、不入队

#### Scenario: 抽取模型未配则明确失败
- **WHEN** `extraction` 段未配 endpoint/model 而尝试抽取
- **THEN** 以清晰错误提示配置抽取模型(不静默产出空图)

### Requirement: extraction 填充图后 planner 检索端到端命中

extraction 填充实体/关系图后,agent 检索在 `use_planner=true`(经 `kb-read-service` 透传,见 `kb-http-quality-passthrough`)时 SHALL 能经 `plan_knowledge_search` + graph_search 命中实体/关系关联的 chunk。extraction SHALL 保持 per-KB opt-in(默认关),graph 检索 SHALL 保持 planner 触发(不新增默认检索开销)。

#### Scenario: 抽取后图检索命中
- **WHEN** 某 KB 已开 extraction 并抽取完成、检索请求 `use_planner=true` 且 query 命中实体/关系
- **THEN** planner 经 graph_search 返回实体/关系关联的 chunk
