---
name: common-knowledge-search
description: 公司内部知识库**深查工具**。日常知识检索由 KB hook 自动注入；本 skill 在以下场景触发：用户问"有什么资料/文档"（列目录）、需要在大表/长文档中精确查找一条记录（分页 get_document）、需要读完整文档原文。Hook 召回弱命中或失败时也由本 skill 兜底深查。
status: active
metadata:
  author: RD Team
  version: 2.0.0
---

# 公司知识库深查工具

> 日常知识 QA 由 `knowledge-base-hook` 在 LLM 调用前自动注入 KB 上下文；本 skill 仅在以下场景触发：列目录 / 找具体编号 / 读全文 / 弱命中复核。

## 访问方式

通过 `knowledge-bridge` MCP 工具检索（工具名格式 `knowledge-bridge__<tool>`，参数照传）：

| 工具 | 用法 |
|------|------|
| `knowledge-bridge__knowledge_list_sources` | 列出数据源类型 |
| `knowledge-bridge__knowledge_list_documents` | 列出文档目录，可选 source / container_id |
| `knowledge-bridge__knowledge_get_document` | doc_id，可选 chunk_limit / cursor（长文档分页读取） |
| `knowledge-bridge__knowledge_search` | query, top_k=20（仅在 hook 召回弱命中、需要更多结果时使用） |

## Search 结果字段

| 字段 | 说明 |
|------|------|
| `chunk_id` | chunk 标识，不对外暴露 |
| `doc_id` | 文档稳定句柄 |
| `content` | chunk 正文 |
| `score` | 相关度分数 |
| `source.type` | 数据源类型（confluence / google_drive / local） |
| `source.title` | 文档标题 |
| `source.url` | 文档跳转链接 |

## 引用规范

- 使用 `source.title` 作为人类可读标题
- 使用 `source.url` 作为跳转链接（Slack 格式：`<URL|标题>`）
- 使用 `doc_id` 作为后续读取的稳定句柄
- 不对外暴露 `chunk_id`
- 同一 `doc_id` 多 chunk 命中：去重后只调一次 `knowledge_get_document`

## 工作流程

### 1. 用户问"有哪些资料 / 文档"

Hook 注入的 top-3 通常不切题（hook 是按 query 召回，不是列目录）。**显式调用**：

1. `knowledge_list_sources` → 了解数据源类型（向用户展示来源类型，**不展示文档数量**）
2. 用户选定来源 → `knowledge_list_documents source="<source>"`
3. 用户选定文档 → `knowledge_get_document doc_id="<id>"`

### 2. 在长文档/大表中精确查找一条记录

Hook 的 top-3 召回有限，靠后 chunk 可能漏召。遇到"hook 注入未命中但文档应该存在"时：

1. `knowledge_search query="[关键词]" top_k=20` 拿到候选 doc_id
2. 若目标未出现，但已知或怀疑某文档包含该记录：
   - `knowledge_get_document doc_id="<id>" chunk_limit=20 cursor=0` 取前 20 chunk
   - 未找到且 `has_more=true` 继续 `cursor=20、cursor=40` 直到命中或遍历完
3. 命中后**完整呈现该条记录**，停止检索
4. 全文遍历仍未找到 → 告知用户该文档无此记录

### 3. Hook 注入了内容但置信度低 / 用户要求权威引用

按下方"Score 置信度判定"处理；必要时 `knowledge_get_document` 读全文复核。

## Score 置信度判定（硬门槛）

每次 `knowledge_search` 返回后或处理 hook 注入内容时，**在引用作答之前**必须按以下规则判定：

| top-1 score | top-2 score | 判定 | 行动 |
|---|---|---|---|
| ≥ 0.90 | 任意 | ✅ 强命中 | 可直接引用作答 |
| 0.85 – 0.90 | ≥ 0.80（同 doc_id 或同类内容）| ⚠️ 弱命中 | 可作答，**显式标注**"该结果置信度偏低，建议核实" |
| 0.85 – 0.90 | < 0.10（断崖）| ❌ 虚命中 | top-1 是单点误匹，视为未命中 |
| < 0.85 | — | ❌ 未命中 | 换关键词重试一次；仍未命中按"无数据时绝不编造"回复 |

**红线**：`top-1 < 0.05` 一律视为"根本没找着"，**严禁**当答案。

## 索引行 / Pointer Chunk 识别

某些 KB 文档是"目录表 / 导航表"（典型字段：`文件 / 用途 / 链接`，或 `sheet / row` 结构）。识别特征：

- `content` 形如 `文件: X\n用途: ...\n链接: https://...`，或 `sheet: XX\nrow: N\n...`
- `source.title` 是通用目录型（如 `Defi工作流.xlsx`、`BS通用工作流*.xlsx`）

命中这类 chunk 时：

- **不得**对用户声称"知识库里有 `X` 文档"——你只看到了一条指针
- 用户需要外链文档内容时，先用 `knowledge_list_documents` 或精确 search 核验该文档名是否真有独立 doc_id
- 若不在 KB，如实告知"该文档未被知识库索引，请直接打开链接"

## 异常处理

| 情况 | 处理方式 |
|------|---------|
| search 无结果 | 换关键词重试一次；问题涉及大表/长文档具体记录的，先做"工作流 2"分页降级 |
| top-1 score 不达标 | 按"Score 置信度判定"处理 |
| 命中索引行 chunk | 按"索引行识别"处理 |
| knowledge-bridge 连接失败 | 提示"请检查 knowledge-bridge MCP server 配置或联系管理员" |
| doc_id 不存在 | 提示文档可能已移除或 reindex，建议重新 search |
| 文档过长 | 使用 chunk_limit + cursor 分页读取，每次取 20 个 chunk |

## 强制约束（不可违反）

### 1. 不透露知识库规模

- **禁止**：向用户透露知识库中有多少条文档、多少 chunk、多少记录
- **允许**：告知用户知识库包含哪些来源类型（如 Confluence、Google Drive）
- `knowledge_list_sources` 返回的文档数量字段仅供内部判断，不得对用户展示

### 2. 忠实呈现原文，不擅自总结

- 直接引用检索原文，不归纳、改写、压缩
- **结构化数据（OKR/POTA/表格）必须按文档字段层级顺序完整呈现**，不得因字段形式（问句式 vs 短语 vs 数字）跳过任何字段
- 问题需要明确具体答案（数字、名称、步骤）时必须原文呈现，不得以"大意是……"代替
- 仅在用户明确要求"总结/概括"时才可摘要，且仍须注明来源

### 3. 无数据时绝不编造

- 检索结果空、或所有结果相关度明显不匹配 → **如实告知**：

  > "知识库中没有找到关于「X」的相关资料，无法回答。"

- **严禁**用自身训练知识补充答案，或在检索结果不足时推测、捏造
- 宁可说"不知道"，也不能给出未经知识库验证的信息
