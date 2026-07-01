## Why

KB 检索质量缺口:**Http provider 路径的质量被钉在裸 hybrid**。`serve.py` 的 `/search` handler **硬编码 `rerank=False`、固定用 `config.default_mode`、不跑 planner**(`serve.py:189-195`)——即便 agent 的 retrieval policy 开了 rerank / 指定了 mode / 开了 planner,经 Http 走 kb-serve 时**全部丢失**。结果:Local provider 能 rerank/planner/graph,Http provider 结构上做不到,质量永远只有裸 hybrid。

而 Http provider 恰恰是 embedding 两端天然一致(同一 kb-service.yaml)、最稳的可用路径。本 change 让 kb-serve 的 `/search` **接收并执行** agent 传来的 mode / rerank / use_planner,使 Http 路径质量与 Local 对齐。

## What Changes

- **`serve.py` /search 接收检索策略**:`SearchRequest` 增 `mode` / `rerank` / `use_planner`(向后兼容,默认 = 服务级 default_mode / False / False)。handler **去掉硬编码 `rerank=False`**,按请求执行:
  - `use_planner=True` → 走 `plan_knowledge_search` + `execute_knowledge_search_plan`(镜像 long_term_ctx Local 路径的 planner 逻辑)
  - 否则 → `kb_runtime.search(mode=<请求 mode 或默认>, rerank=<请求 rerank>)`
- **`knowledge_base/runtime.py`**:`search` 已有 `mode`/`rerank` 形参(:147-148),确保 serve 透传接通;planner 经 public API(`plan_knowledge_search`/`execute_knowledge_search_plan`)调用,不复制检索逻辑。
- **`long_term_ctx` 的 HttpKnowledgeProvider 请求体**:把 agent retrieval policy 的 `mode` / `rerank` / `use_planner` **随请求发给 kb-serve**(现在只发 query/kb_ids/limit/mode 的一部分)。

净效果:Http provider 路径**可 rerank、可指定 mode、可 planner/graph**——质量与 Local 路径对齐;策略由 agent policy 决定、经 HTTP 传递、由 kb-serve 执行。

## 边界(与并行的 B `kb-embedding-consistency` 划清,严禁越界)

本 change **只动**:`knowledge_base/serve.py`、`knowledge_base/runtime.py`(透传)、`long_term_ctx/__init__.py` 的 **HttpKnowledgeProvider 请求体构造区域**。

**严禁触碰(B 的地盘)**:`retrieval/search.py`、`core/migrations.py`、`core/store.py`、`vector_store/runtime.py`、`ingest/runtime.py`、`agent_config.py`、`kb-service.yaml.example`,以及 `long_term_ctx` 的 `_retrieve_with_timeout` 错误处理区域(那是 B 的 embedding 校验错误传播改动)。`long_term_ctx/__init__.py` 是唯一与 B 共享的文件——只改 HttpKnowledgeProvider 请求体,不碰其它区域;后 merge 的分支 rebase on main 解小冲突。

## Capabilities

### Modified Capabilities
- `kb-read-service`:`/search` wire 协议接收并执行 per-request `mode` / `rerank` / `use_planner`;去掉硬编码 `rerank=False`;Http 路径质量与 Local 对齐。

## Impact

- **owning area**:`knowledge_base/serve.py`、`knowledge_base/runtime.py`(透传)、`long_term_ctx/__init__.py`(HttpKnowledgeProvider 请求体)。spec `kb-read-service`。**不碰 platform**。
- **public surface**:`/search` 请求体增 `mode`/`rerank`/`use_planner`(可选,向后兼容);wire 协议两端对称扩展。
- **owned tables / config / 迁移**:无。
- **cross-module / 解耦**:不新增依赖;检索逻辑仍经 `knowledge_base` public API,不复制。
- **依赖关系**:可与 B 并行(边界已划);与 rerank 后端(Infinity)联动属 Tier-2,本 change 只做"透传 + 执行",rerank backend 是否启用由配置决定。
- **测试**:serve `/search` 接收 mode/rerank/use_planner 并执行的单测/集成测;HttpKnowledgeProvider 发全字段的单测;`make test-pr` + `make test-integration-ci` 全绿。
