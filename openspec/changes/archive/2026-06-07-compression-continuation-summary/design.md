## Context

压缩逻辑在 `runtime/context.py`：`_compress` 三层切分（head / summary / tail），`_build_summary_prompt`(446) 当前是英文自由文本，`_select_tail`(379) 按 `fixed = estimate_tokens(head) + _SUMMARY_OVERHEAD` 投影选尾部。C2 已提供 `session_mgr.read_todo({sid}.todo)`。

## Goals / Non-Goals

**Goals:** 结构化摘要模板（保留续跑要素）；压缩丢中段时把未完成 todo 逐字保留进上下文。

**Non-Goals:** 不做按模型窗口预算 / overflow 接线 / 压缩后死循环守卫 / 工具结果 prune（均归 C3b）；不改 anti-flap / 阈值。

## Decisions

### D1：结构化摘要模板（两分支同结构）
`_build_summary_prompt` 改为指示 LLM 输出固定分节（Goal / Completed / In Progress·Pending / Key Findings & Files / Next Steps），显式要求逐字保留未完成工作与下一步。首次与增量（`prev_summary`）两分支共用同一组分节；增量要求"并入既有分节"。Prompt 保持英文（跨模型稳健），与现状一致。

### D2：active-task 续跑块
新增 `_active_task_block(session_id)`：lazy import `session_mgr.read_todo`，取状态非 `completed` 的条目，逐字渲染成一条 `{"role":"system", content: _ACTIVE_TASK_PREFIX + 列表}`；无 session_id / 无未完成 / 读异常 → 返回 None。在 `_compress` 的 **summarized** 与 **degraded** 路径注入：`result = [*head, *active, summary_or_notice, *tail]`（`no_middle` 路径不注入——未丢任何内容）。`active` 的 token 经新增的 `extra_fixed` 计入 `_select_tail` 投影，避免尾部超 target。

### D3：identity 不变式
active-task 块是**新建 dict**，不在 `head_ids`/`tail_ids` 集合内，不参与 `_keep_tail` 的 `m is tail[0]` 判定，不破坏现有按 `id()` 的 head/tail 去重。

### D4：安全退化
无 session_id（CLI 一次性）、无未完成 todo、或读 `.todo` 失败 → 不注入块、不报错，压缩行为与未引入本能力时一致（零惊吓）。

## Risks / Trade-offs

- **[Risk] `_compress` 是关键路径** → active-task 块仅是 head 后插入一条合法 system 消息，不动 head/middle/tail 切分逻辑；新增分支用退化保证不改变既有路径。
- **[Risk] token 投影遗漏 active 块** → 把其 token 计入 `_select_tail` 的 fixed，尾部相应收缩；与现有"tail 允许略高于 target"的 relaxation 一致。
- **[Trade-off] active-task 仅在压缩时注入**（非每轮）→ 平时模型用 `todo(get)`；压缩时注入避免"中段被摘掉后丢失未完成项"，这是本能力的核心场景。
