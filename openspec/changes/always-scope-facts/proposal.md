## Why

当前 facts 全部走向量检索召回，行为指令类 fact（如 `response_style | 添加 xin 标识在句末`）因与用户 query 语义无关而频繁漏召，导致 agent 随机遗忘用户设定的行为规则。行为指令的本质是"无条件生效"，与语义相关性无关，放在向量召回池里是错误的存储语义。

## What Changes

- facts 表新增 `scope` 字段（`situational` | `always`），默认 `situational`
- `always` facts 每轮对话无条件注入 system context，跳过向量检索
- `always` facts 按 relation 分两层管理：
  - **soft 白名单**（`response_style`, `tone`, `format`, `language`, `output_format`）：设上限 15 条，超限按 `updated_at` 最旧 retract
  - **hard（钉死）**：显式清单（`never_do`, `always_do`, `security`, `approval_required`）+ 未命中白名单的未知 relation 默认 hard，不参与淘汰
- facts 提取 pipeline 新增 scope 判断：行为指令 → `always`，事实性偏好 → `situational`
- `build_context` 注入顺序：先无条件注入 `always` facts（独立 section），再向量检索补充 `situational` facts
- schema migration 回填：现有 `relation` 在 soft 白名单或 hard 清单中的 facts 按规则设置 scope，其余保持 `situational`

## Capabilities

### New Capabilities

- `facts-always-scope`：facts scope 字段、always facts 存储与无条件注入、分层淘汰策略

### Modified Capabilities

- `memory-layer`：facts 提取 pipeline 新增 scope 输出字段
- `long-term-ctx`：`build_context` 新增 always facts 无条件注入路径

## Impact

- **数据库**：`facts` 表 schema 变更（加 `scope` 列），需 forward-only migration（`agent_state_migrations.py`）
- **受影响模块**：`memory/facts_store.py`、`memory/facts_pipeline.py`、`memory/facts_search.py`、`long_term_ctx/__init__.py`
- **无 breaking change**：`scope` 默认 `situational`，现有行为不变；新增注入路径为追加，不替换
- **测试**：unit（facts_store、facts_pipeline、long_term_ctx）+ integration（always facts 端到端注入验证）
