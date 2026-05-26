# knowledge-base

> 写作提醒：功能描述只写可观察的行为，不写内部实现细节。验收标准只写端到端可验证的行为。

## 概述

企业文档知识的导入、索引与检索，让 agent 能够基于企业内部文档回答问题。

**负责**：文档导入与分块、向量索引构建、按查询召回相关文档片段。

**不负责**：注入 system prompt 的协调与 token 预算（→ long_term_ctx）、用户个人记忆（→ memory）。

**调用关系**：
- 依赖：vector_store（向量索引）、config
- 被依赖：long_term_ctx（检索注入内容）

## 现状

尚未实现。

## 规划中（v1.0）

- [ ] **文档导入**：支持将文档导入知识库
  - 支持格式：Markdown、纯文本、PDF
  - 导入后异步处理（分块 + embedding），不阻塞调用方

- [ ] **分块与向量索引**：文档内容分块后 embedding，写入共享 vector_store
  - 每个 chunk 保留来源文档信息（文件名、chunk 位置）

- [ ] **向量相似度检索**：根据查询召回最相关的文档片段
  - 对外接口：`search(query: str, scope: str) → List[KnowledgeChunk]`
  - 由 long_term_ctx 在对话开始时调用

- [ ] **作用域隔离**：支持 per-tenant 或 per-agent 两种隔离粒度
  - per-tenant：整个租户共享同一知识库
  - per-agent：不同 agent 使用不同知识库，适合多业务线场景

## 验收标准

**场景 1：文档导入后可被检索**
- Given：管理员导入一份 Markdown 文档
- When：用户提问与文档内容相关
- Then：long_term_ctx 通过 knowledge_base.search() 召回相关片段，agent 回答中体现文档内容

**场景 2：导入不阻塞**
- Given：管理员上传一份较大的 PDF
- When：导入请求返回
- Then：API 立即返回成功，分块与 embedding 在后台执行

**场景 3：作用域隔离**
- Given：agent A 和 agent B 分别绑定不同知识库
- When：两个 agent 分别检索相同 query
- Then：各自只召回自己作用域内的文档片段，互不干扰

## 待决问题

- [ ] 分块策略：固定 token 大小（如 512 tokens，overlap 50）vs 语义分块（按段落/标题）？（负责人：待认领）
- [ ] 文档更新机制：重新导入同名文档时覆盖旧 chunk，还是版本化保留？（负责人：待认领）
- [ ] 默认作用域粒度：per-tenant 还是 per-agent？（负责人：待认领）
