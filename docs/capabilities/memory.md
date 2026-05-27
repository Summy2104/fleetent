# memory

> 写作提醒：功能描述只写可观察的行为，不写内部实现细节。验收标准只写端到端可验证的行为。

## 概述

per-user 语义记忆的提取、存储与检索，让 agent 在多次对话中积累用户知识、越用越懂用户。

**负责**：从对话中提取用户相关事实，按类型结构化存储，支持向量相似度检索。

**不负责**：企业文档知识（→ knowledge_base）、注入 system prompt 的协调与 token 预算（→ long_term_ctx）、记忆质量的定期优化（→ reflection）。

### 记忆系统全局架构

fleetent 的记忆系统借鉴认知科学的四类记忆划分，每类由不同模块负责：

| 类型 | 内容 | 存储位置 | 负责模块 |
|------|------|---------|---------|
| **语义记忆** | 用户身份、偏好、临时状态等跨 session 事实 | SQLite `memory_items` + vector_store | `memory_layer`（本模块）|
| **情节记忆** | 对话与工具执行的完整历史轨迹 | `traces.jsonl` | `eval_logger` |
| **程序记忆** | agent 完成特定任务的技能与方法 | `skills/` 目录 | `skill_registry` |
| **工作记忆** | 当前 session 的对话上下文（session 结束即释放） | 内存 | `context_mgr` |

本模块（`memory_layer`）只负责**语义记忆**，即按 `identity` / `preferences` / `context` 三类结构化存储的用户事实。其余三类由各自模块独立管理，`reflection` 跨模块读取情节记忆（traces）与语义记忆（memory_items）来做质量优化。

**调用关系**：
- 依赖：model_router（`memory_extraction` task，默认轻量模型，可通过 config 覆盖）、vector_store（向量索引）、config
- 被依赖：long_term_ctx（检索注入内容）、reflection（读取现有记忆、写回优化结果）

## 关键流程

两条独立流程，分别在对话结束后和对话开始前触发。

```mermaid
flowchart TD
    subgraph extract["提取流程（异步，SSE done 后触发）"]
        A[SSE done] --> B[LLM 提取新事实]
        B --> C{与已有同类记忆比较}
        C -->|无冲突| D[追加新条目]
        C -->|有冲突| E[合并或替换旧条目]
        D --> F[Re-embed → 更新 vector_store]
        E --> F
    end

    subgraph search["检索流程（对话开始时，由 long_term_ctx 触发）"]
        G[long_term_ctx 调用 search] --> H[Embed query]
        H --> I[vector_store 向量检索]
        I --> J[过滤已过期条目]
        J --> K[返回 MemoryItem 列表]
    end
```

## 数据模型

```sql
memory_items (
  id          TEXT PRIMARY KEY,  -- UUID
  user_id     TEXT,              -- → users.id
  type        TEXT,              -- "identity" | "preferences" | "context"
  content     TEXT,              -- 事实内容
  created_at  DATETIME,
  updated_at  DATETIME,
  expires_at  DATETIME           -- 仅 context 类有值；identity / preferences 为 NULL
)
```

向量 embedding 存储在 vector_store，以 `memory_item.id` 为 key，不写入此表。

## 接口定义

```python
@dataclass
class MemoryItem:
    id: str
    user_id: str
    type: Literal["identity", "preferences", "context"]
    content: str
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None


async def search(user_id: str, query: str, limit: int = 10) -> list[MemoryItem]:
    """按语义相似度返回最相关的记忆条目，自动过滤已过期条目。由 long_term_ctx 调用。"""


async def extract_and_update(user_id: str, conversation: list[dict]) -> None:
    """从对话中提取事实，冲突检测后写入。SSE done 后异步调用，不阻塞响应。"""
```

## 现状

- ✅ **事实提取**：对话结束后异步提取用户相关事实，写入 JSONL
  - 使用 model_router 的 `memory_extraction` task，默认路由到轻量模型
  - 提取不阻塞主响应，在 SSE done 之后异步执行
  - 存储路径：data/users/{user_id}/memories.jsonl

- ✅ **记忆注入**：每次 run() 开始前加载最近 20 条记忆注入 system prompt
  - 固定 top-20，无检索，无排序
  - v1.0 后注入由 long_term_ctx 统一协调，memory_layer 只暴露 search() 接口

## 规划中（v1.0）

- [ ] **结构化记忆类型**：按类型区分存储，取代 free-text JSONL 平铺
  - `identity`：身份事实（姓名、职位、技能）— 永久有效
  - `preferences`：工作偏好（风格、输出格式偏好）— 长期有效
  - `context`：临时状态（当前项目、进行中任务）— TTL 30 天，过期自动失效

- [ ] **冲突检测与合并**：新提取的事实与已有同类记忆比较，按类型规则决定处理方式
  - `identity` / `context`：新覆盖旧（身份和状态以最新为准）
  - `preferences`：区分**明确陈述**（"我以后都想要..."）和**一次性请求**（"这次帮我..."）
    - 明确陈述 → 更新记忆
    - 一次性请求 → 不更新记忆，当前 session 上下文处理即可
  - 判断在提取 prompt 内完成，LLM 输出 `update` 或 `ignore`，不额外调用

- [ ] **向量相似度检索**：通过共享 vector_store 对记忆条目建立向量索引
  - 对外接口：`search(user_id: str, query: str) → list[MemoryItem]`
  - 由 long_term_ctx 在对话开始时调用

- [ ] **embedding 模型**：自托管本地模型（bge-m3 或 multilingual-e5）
  - 禁止使用 OpenAI Embeddings 等云托管专有服务

## 验收标准

**场景 1：记忆跨 session 持久化**
- Given：用户在第一次对话中告知"我是后端工程师"
- When：用户开始第二次对话（新 session）
- Then：agent 在新 session 中能体现对用户身份的了解，无需用户重复说明

**场景 2：提取不阻塞响应**
- Given：一次正常对话
- When：agent_loop.run_stream() 发送 SSE done
- Then：记忆提取在后台执行，不延迟 done 事件

**场景 3：冲突检测（v1.0）**
- Given：用户记忆中已有 identity 条目"用户是后端工程师"
- When：用户在新对话中说"我现在转做产品了"
- Then：旧条目被替换，不出现两条矛盾的身份记忆

**场景 4：向量检索（v1.0）**
- Given：用户有 50 条历史记忆，当前话题是"Python 调试"
- When：long_term_ctx 调用 memory_layer.search()
- Then：返回与"Python 调试"相关的记忆条目，而非固定最近 20 条

**场景 5：context 类记忆过期（v1.0）**
- Given：用户 35 天前提到"正在做支付系统项目"（context 类，TTL 30 天）
- When：该记忆被检索
- Then：不出现在返回结果中

## 测试边界

测试分两层，职责不同。

**第一层：结构正确性（CI 自动运行，LLM 全部 mock）**

需要单元测试的行为：
- 冲突检测：identity 类新事实导致旧条目被替换，不产生重复
- preferences 信号强度：mock LLM 返回 `update` 时更新记忆，返回 `ignore` 时不更新
- TTL 过期过滤：search() 不返回 expires_at < now 的条目
- 类型分类：LLM 提取结果被正确归类到 identity / preferences / context
- 提取异步性：extract_and_update 不阻塞调用方（fire-and-forget）

需要 mock 的依赖：
- `model_router.get_async_client_and_config`：隔离所有 LLM 调用（提取和冲突判断）
- `vector_store`：隔离向量索引读写
- SQLite DB 路径：`monkeypatch` 到 `tmp_path`，绝不触碰 data/

**第二层：提取质量（定期手动触发，使用真实 LLM）**

用合成对话 fixture 验证端到端提取质量：
- 准备若干包含已知事实的多轮对话（如"用户告知职位、偏好、当前项目"）
- 跑完整提取流程，断言关键事实出现在记忆中且无幻觉条目
- 适合在升级 LLM 模型或修改提取 prompt 后触发，不纳入日常 CI

## 待决问题

- [ ] 冲突判断粒度：同 type 下全量比较，还是只对语义相似度超过阈值的条目做冲突检测？（负责人：待认领）
- [ ] context TTL 起算点：首次提及时间，还是最后一次提及时间？（负责人：待认领）
- [ ] 记忆条数上限：v1.0 先设软监控阈值（超出记告警日志），还是直接按 type 设硬上限？如设硬上限，identity / preferences 各多少合适？超出时由 reflection 批量合并，还是 memory_layer 内联驱逐？（负责人：待认领）

