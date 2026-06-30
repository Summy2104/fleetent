## Why

KB 缺口审计的 **P0 可用性悬崖**:embedding 身份本该是 KB 向量的属性,但当前设计让 **agent 自带 embedding**(`agent.yaml` 路由),与 **ingest 用的 embedding**(`kb-service.yaml`)是两份独立配置,且 **KB 自身不记录**它是用哪个模型/维度建的(`knowledge_bases` 表无 embedding 列,已核)。后果:

- **维度不同** → embedding 调用抛错 → 被 `_retrieve_with_timeout` 吞成空 → **静默查不到**
- **维度同、模型不同**(最阴险)→ 不报错,向量空间不可比 → **召回全是噪声、答错且无提示**

A(`kb-manual-ingest-cli`)已让文档**灌得进**;但不解这条,灌进去的内容 agent **查不到或查到噪声**——A+B 配套才端到端可用。本 change 取**检测**路线:把 embedding 身份**钉到 KB**,ingest 与检索两端校验,不匹配**响亮报错**,并对齐默认配置让常见场景开箱一致。

(注:Http provider 路径本就一致——ingest 与 kb-serve 读同用 kb-service.yaml;坏的是默认 Local 路径。本 change 给两条路都加 KB 身份护栏,主救 Local。)

## What Changes

- **KB 记录 embedding 身份**:`knowledge_bases` 表加 `embedding_model TEXT` + `embedding_dimensions INTEGER`(KB_MIGRATIONS 追加一个 forward-only 版本;非 Alembic)。首次有向量写入(首次 ingest)时 stamp 当前 embedding 的 model+dimensions。
- **ingest 端校验**:再次 ingest 时,若当前 embedding 的 model/dimensions ≠ KB 已记录的 → **拒绝并清晰报错**(不把两个模型的向量混进一个 KB)。
- **检索端校验**:query 向量化前(`retrieval/search.py:122 embed_text` 之前),比对当前 embedding 的 model/dimensions 与 KB 记录的 → 不匹配 **硬失败 + 清晰报错**(指出 KB 建库 embedding vs 当前检索 embedding,指引对齐),**取代当前的静默空/静默噪声**。
- **对齐默认**:`agent_config` 默认 embedding 路由 与 `kb-service.yaml.example` 的 `embedding`(现为 `default-embedding/dim64` vs `bge-small/dim384`,天生打架)对齐为**同一模型+维度+端点**,使开箱常见场景两端一致。
- **deterministic 后端**:离线/测试用的 deterministic embedding 无真实 model 名,按约定身份(如 `deterministic/<dims>`)记录与比对,避免误伤测试路径。

不做:**预防**(检索侧强制改用 KB 记录的 embedding 去检索)——更省心但跨 agent/KB 配置边界、更侵入,留作 v2;本 change 只做检测 + 默认对齐,把悬崖从"静默错"变成"响亮错 + 常见场景开箱可用"。

## Capabilities

### Modified Capabilities
- `knowledge-base`:KB 自描述其 embedding 身份(model+dimensions);ingest stamp + 拒绝混模型;检索校验不匹配则硬失败(替代静默)。

## Impact

- **owning area**:`knowledge_base/`(`core/migrations.py` 加列、ingest 写入处 stamp、`core/store.py`/`management` 读写身份、检索 `retrieval/search.py` 校验)、`vector_store`(暴露当前 embedding 的 model+dimensions 供校验)、`agent_config` + `kb-service.yaml.example`(默认对齐)。**不碰 platform**。
- **owned tables**:`knowledge_bases` 加 2 列(嵌入式 forward-only 迁移,向后兼容:旧 KB 列为 NULL → 视为"未记录",首次匹配时回填或宽松放行一次再 stamp)。
- **行为变更**:embedding 不匹配从**静默空/噪声**改为**硬失败报错**——这是刻意的(把不可用悬崖暴露成可诊断错误)。
- **config**:example 默认 embedding 两端对齐;现有部署若两端本就不一致,升级后检索会**响亮报错**(而非继续静默错)——正是本 change 的目的,运维据错对齐。
- **cross-module / 解耦**:不新增依赖;不碰 platform。
- **测试**:新增 stamp/ingest-reject/retrieval-mismatch-fail/default-alignment 单测 + 集成测;`make test-pr` + `make test-integration-ci` 全绿。
- **依赖**:与 A 配套构成端到端;可独立落,但价值在 A 之上显现。
