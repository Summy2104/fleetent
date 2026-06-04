## Context

`agent_loop` 的提示组装（`run_sync` 行 ~194-201、`run_stream` 行 ~225-230）当前：
```python
full_system = f"{memory_ctx}\n\n{system_prompt}" if memory_ctx else system_prompt
matched = match_skill(user_input)
if matched:
    full_system = f"{full_system}\n\n{load_skill(matched)}"
messages = [{"role": "system", "content": full_system}, {"role": "user", ...}]
```
即把 `memory_ctx`（每请求 `load_memories` 而来）与 matched skill（每 `user_input` 不同）拼到 **system 消息最前**。LLM 调用 `_call_with_fallback` / `_stream_with_fallback` 传 `messages` + `tools=schemas`，未取用 `usage` 的缓存字段。

提示缓存（prompt caching）按**前缀**工作：自托管 vLLM 的自动前缀缓存（APC）、OpenAI 的自动缓存均无需标记，靠前缀逐 token 匹配命中。前缀里只要有一处变，其后全部 miss。现状把可变内容放最前 → 前缀几乎永不稳定 → 缓存形同未启用。

本 change 是成本/延迟优化，与 AR12（双阈值压缩，理由含"保护 prompt 缓存"）配套。约束（CLAUDE.md）：无 AI 框架、无新依赖、单一 OpenAI 兼容 SDK、mypy strict、TDD、LLM 调用 mock。

## Goals / Non-Goals

**Goals:**
- 重排提示组装：稳定 `[base system + tools]` 置前作可缓存前缀，可变 `[memory、skill]` 后置，不改各自功能效果。
- 从 `usage` 提取缓存指标记入 trace，建立命中率可观测。
- 后端无关：依赖自动前缀缓存，不引入 `cache_control` 标记、不引入 native SDK。
- 与 AR12 协调：压缩保留可缓存头部。

**Non-Goals:**
- 不引入 Anthropic `cache_control` 标记或 native Anthropic SDK（见 D1）。
- 不为 Anthropic 云端专门优化（生产 on-prem 后端是自托管 vLLM）。
- 不实现 AR12 的压缩本身（仅声明"保留可缓存头部"的协调要求）。
- 不自建缓存层；不改 `match`/`load`/`load_memories` 的功能语义。

## Decisions

### D1：走自动前缀缓存，不用 `cache_control` / 不换 SDK
依赖后端的自动前缀缓存（vLLM APC、OpenAI 自动缓存），fleetent 侧只保证前缀稳定，不传任何 provider 专有缓存标记。
**为何**：on-prem 生产后端为自托管 vLLM（数据不出内网，model_router 注释即指明 flip 到 vLLM），vLLM 自动前缀缓存走现有 OpenAI 兼容 SDK 即可；`cache_control` 是 Anthropic native 特性，只服务 Anthropic 云（非生产目标），且需 native SDK，破坏"单一 OpenAI 兼容 SDK"原则。
**Alternatives**：①Anthropic `cache_control` 标记 + native SDK——被否（后端专有、破坏 SDK 原则、优化错误对象）；②自建语义缓存层——被否（重复造轮子、与后端缓存重叠）。

### D2：按稳定度排序的提示组装
组装顺序由稳定到可变：**`base system`（最稳）→ tools（随调用稳定）→ memory（会话内大体稳定）→ matched skill（每轮可变）→ 对话消息**。具体：
- `base system`（`_SYSTEM` 或 agent 的 `system_prompt`）作为**第一条 system 消息**，内容不含 memory/skill，跨请求稳定 → 构成可缓存前缀。
- `memory_ctx` 与 matched skill 注入为**其后的独立内容**（追加为后续 system 消息，或并入首个 user turn 之前的上下文消息），而非塞进首条 system。
- tools schema 已单独以 `tools=` 传入、本就稳定，不动。

**为何**：可缓存前缀长度 = 从头到第一处可变内容。把可变项后移，至少 `base system (+tools)` 稳定可缓存；会话内 memory 稳定时前缀更长。功能上 memory/skill 仍进入提示、效果等价，仅位置变化。
**Alternatives**：①保持现状全拼进首条 system——被否（前缀永不稳定）；②把 memory/skill 放到对话最后——被否（语义上它们是上下文/指南，应在用户消息之前呈现给模型）。
**Open**：memory/skill 后置的确切承载形式（独立 system 消息 vs 首个 user turn 前缀）需在实现首步对照 vLLM/OpenAI 对多条 system 消息的前缀缓存行为核实后定；以"不改功能效果 + 最大化稳定前缀"为准。

### D3：从 usage 提取缓存指标记入 trace
`log_run` 增加 `cache_tokens: dict | None = None`（加性、默认 None、非 None 写入 entry，同 `stop_reason`/`error_category` 模式）。`run`/`run_stream` 收尾时从 `response.usage` 尽力提取缓存字段（Anthropic 风格 `cache_read_input_tokens`/`cache_creation_input_tokens`、OpenAI 风格 `prompt_tokens_details.cached_tokens`），字段缺失则不记。
**为何**：建立"命中率基线"、验证前缀稳定优化是否生效；复用唯一 trace 出口，改动最小。后端字段形态各异，尽力提取、缺失安全降级。
**Open**：各后端 `usage` 上缓存字段的确切路径/命名——实现首步核实（vLLM / OpenAI 兼容端点实际返回）。

### D4：与 AR12 协调——压缩保留可缓存头部
AR12 的分层保留压缩在改写历史时，MUST 保留可缓存头部（base system + tools + 稳定前缀），仅压缩对话尾部，避免每次压缩都改写前缀致缓存全失效。本 change 声明该要求，分层保留的实现属 AR12；因此**本 change 排在 AR12 之后**，确保压缩与缓存稳定一致设计。
**为何**：压缩与缓存是同一前缀的两个使用者；不协调则压缩会反复打掉缓存（正是 AR12 想避免却没落实的）。

## Risks / Trade-offs

- [重排提示顺序意外改变模型行为（system 拆成多条 / memory-skill 位置变化）] → 仅调整顺序、不改内容集合；用例断言 memory/skill 仍生效、base system 在前；对照后端对多 system 消息的处理。
- [会话内 memory 实际每轮变化导致前缀仍短] → 即便如此，base system(+tools) 仍稳定可缓存，优于现状的零缓存；memory 稳定时收益更大。
- [缓存指标字段因后端不同而取不到] → 尽力提取、缺失记 None，不报错；测量是观测增强，非功能依赖。
- [与 AR12 未同步导致压缩仍打缓存] → 本 change 排 AR12 之后并显式声明"保留可缓存头部"要求，二者一起验收。

## Open Questions

- memory/skill 后置的承载形式（独立 system 消息 vs user turn 前缀）——实现首步据后端前缀缓存行为核实。
- 各后端 `usage` 缓存字段命名/路径——实现首步核实。
