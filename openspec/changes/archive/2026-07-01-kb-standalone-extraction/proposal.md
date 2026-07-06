## Why

extraction/graph 管线**已建但默认关 + 有 standalone 缺口**:实体/关系抽取(`extraction.py`)、per-doc 入队(ingest 侧)、worker 抽取 handler(`worker.py:258`)、图检索(`graph_search.py` 读 `kb_entities`/`kb_entity_mentions`/`kb_relations`)全部就绪,C 也让 `use_planner` 经 Http 可传。但:

1. **`extraction_enabled` 只能在建 KB 时设,没有 setter**——存量 KB 无法开启抽取。
2. **回填 CLI 绑在 platform**(`fleetent platform kb extract-entities`)——standalone 无入口;且 auto-extract 只对**新 ingest** 生效,**存量文档不会被抽**(backlog 记载的"开 extraction 后需手动回填")。
3. **抽取模型 example 未预置**;没验证过 e2e。

用户确认有**实体/关系型检索需求**,故激活这条:补 standalone"开启+回填"入口、预置抽取模型、验证 e2e。图检索仍 planner-gated(靠 C,不新增默认开销)。

## What Changes

- **standalone CLI**(镜像 A 的 `kb-ingest`):`fleetent kb extract --config <kb-service.yaml> --kb <id> [--wait]`:
  - **开启**:置该 KB `extraction_enabled=true`(补 `KnowledgeStore` setter——现仅 create 时可设)。
  - **回填**:遍历该 KB 存量文档(`list_documents`),**每 doc 入队一个 `extraction` job**(`connector_ref={"document_id": id}`,与 ingest 侧 auto-enqueue 同形),由 **kb-worker 单写者**抽取(不进程内直写 kb.db,守单写者纪律)。
  - `--wait`:阻塞轮询,打印 documents/entities/relations 计数;超时提示查 kb-worker。
  - 纯 KB 服务侧,不依赖 platform。
- **抽取模型 example 预置**:`kb-service.yaml.example` 的 `extraction` 段预置(默认 `enabled: false`,endpoint 指向本地/自托管抽取模型,如 ollama;运维填模型 + 开启即用)——同 rerank/embedding 套路。
- **e2e 验证**:集成测——开 extraction → ingest/回填 → `kb_entities`/`kb_relations` 被填 → planner(`use_planner=true`)graph 查询检索到实体关联的 chunk。

不做:改 graph 触发门(仍 planner + 启发式,靠 C 传 `use_planner`);extraction 默认全局开(仍 per-KB opt-in,抽取费 LLM);平台侧 `extract-entities` CLI(保留,本 change 只补 standalone 对应物)。

## Capabilities

### Modified Capabilities
- `kb-standalone-ingest`:新增 standalone **手动 extraction 命令**(开启 per-KB extraction + 对存量文档入队回填,worker 单写者执行);抽取模型 example 预置。
- `knowledge-base`:`extraction_enabled` 可对存量 KB 开启(setter);extraction 填充实体/关系图后,planner graph 检索可端到端命中。

## Impact

- **owning area**:`knowledge_base/`(`core/store.py` setter、新 `kb-extract` CLI、回填入队逻辑)、`__main__.py`(顶层 `kb-extract` 分发)、`kb-service.yaml.example`(extraction 段)。**不碰 platform**。
- **public surface**:新增 CLI `fleetent kb extract`;`kb-service.yaml` extraction 段 example 预置(默认关,向后兼容)。
- **owned tables**:无新增;写既有 `knowledge_bases.extraction_enabled` + 由 worker 写 `kb_entities`/`kb_entity_mentions`/`kb_relations`。
- **行为变更**:extraction 仍默认关、per-KB opt-in;开启后新 ingest 自动抽、存量经 `kb-extract` 回填。
- **cross-module / 解耦**:不新增依赖;回填走既有 `extraction` job + worker,不复制抽取逻辑;不碰 platform。
- **依赖**:图检索端到端 = 本 change(填图)+ C(Http 传 use_planner)+ 运维配抽取模型 + 开 planner。
- **测试**:setter、CLI 入队回填、e2e(抽取→图填充→planner graph 命中)单测/集成测;`make test-pr` + `make test-integration-ci` 全绿。
