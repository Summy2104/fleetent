## Context

`context_mgr._compress`（context_mgr.py 行 103-120）当前做隐式二分：`system_msgs = [m for m in messages if _role(m)=="system"]`、`conv_msgs = [非 system]`；`tail = _select_tail(conv_msgs, keep_recent, target, system_msgs)`；`to_summarize = conv_msgs[:len-len(tail)]`；最终 `[*system_msgs, summary_msg, *tail]`。`_select_tail`（行 123-143）把 `system_msgs` 的估算与 `_SUMMARY_OVERHEAD_TOKENS` 计入 `fixed`，从 `keep_recent` 起向下收缩尾部直到投影 `<= target`，下界 1 条。`_keep_tail`（行 172-182）用 identity check（`m is tail[0]`）保 tool-pair 完整。

**问题定位**：头部只含 `role==system` 的消息。用户的**初始意图消息**通常是会话第一条 `user` 消息，它落在 `conv_msgs` 的最前面，因而进入 `to_summarize` 被 LLM 摘要。摘要可能丢失或改写初始意图，导致后续轮次偏离用户真正目标。

本 change 属 v1.0 agent-runtime「上下文压缩增强 / 分层保留改进（AR13）」，直接构建在 AR12 双阈值之上，是压缩增强管线 AR15（清理）→ **AR13（分层切分）** → AR14（增量摘要）的中间环节。本次只负责「切分成三层并保护初始意图」，不涉及增量摘要持久化（AR14）与压缩前规则清理（AR15）。

**依赖与归档顺序**：本 change 依赖 AR12（compression-dual-threshold）的双阈值已在 `context_mgr` 代码中生效（`maybe_compress` 以 `Tmax` 触发、`_select_tail` 以 `Tretained` 为目标线）。AR12 截至本 change 尚未归档、其 spec 亦未 sync 进 `openspec/specs/context-compression-threshold/`，因此本 change **不**对该 spec 声明 MODIFIED（否则归档时找不到目标需求，且会与 AR15 对同一「目标线」需求的修改互相覆盖）。本 change 的全部增量以自有 capability `compression-layered-retention` 内的 ADDED 需求叠加，不重写 AR12 既有需求。管线归档顺序为 **AR15 → AR13 → AR14**（清理 → 分层切分 → 增量摘要）。

约束（CLAUDE.md）：禁止 AI 框架；禁止 ORM；禁止全局可变状态（头部范围若可配则经 config dict / monkeypatch 注入，不用模块级可变量）；新模块结构 import → 常量 → 数据类 → 函数；mypy strict；行长 100；TDD Hard Gate；LLM 摘要单测必须 mock（`patch get_client_and_config`）。

## Goals / Non-Goals

**Goals:**
- 把 `_compress` 的隐式二分显式化为「头部 / 中段 / 尾部」三层。
- 头部 = 系统提示消息 + 用户初始意图消息，完整保留，MUST NOT 进入摘要。
- 中段 = 头部与尾部之间的早期对话，交 `_summarize` 生成一条摘要消息。
- 尾部沿用 `_keep_tail` 的 tool-pair 完整性与 identity check。
- 最终序列顺序为 `[头部完整..., 摘要, 尾部完整...]`，对 LLM 合法。
- `Tretained` 目标线达成时把头部完整层计入固定投影。
- 退化场景（中段为空 / 会话过短）不产生空摘要、不破坏序列。

**Non-Goals:**
- 不实现增量摘要与摘要持久化（AR14，独立 change）。
- 不实现压缩前轻量清理（AR15，独立 change）。
- 不改 `Tmax` / `Tretained` 触发与目标线语义、手动 / 错误触发入口、阈值注入契约。
- 不改 `_summarize` 的 LLM 调用方式、`_keep_tail` 的 identity check 算法、`estimate_tokens` 口径。
- 不引入新依赖；新增的 `compression_initial_intent_max` 为**带默认值（2）的可选 Settings 字段**，非必填，不破坏既有部署。

## Decisions

### D1：三层切分显式化，头部纳入初始意图
`_compress` 重构为先析出三层再组装：
- 头部 `head`：系统提示类 `role=="system"` 消息 + 用户初始意图消息（见 D2 识别规则），按原始顺序，完整保留。**排除压缩自产的摘要消息**（见下「与 AR14 的衔接约定」）。
- 尾部 `tail`：经 `_keep_tail` 选取的最近消息（沿用现算法与 identity check）。
- 中段 `middle`：`messages` 中既不在 `head` 也不在 `tail` 的剩余对话消息，交 `_summarize`。
- 组装：`[*head, summary_msg, *tail]`，其中 head 已按原顺序含 system 与初始意图。

**与 AR14 的衔接约定（头部识别排除压缩自产摘要消息）**：现状 `_compress`（context_mgr.py:108）以 `system_msgs = [m for m if _role(m)=="system"]` 收集**全部** system 消息——这会把上一次压缩产出的摘要消息（`role=="system"`、content 以 `[Earlier conversation summary]` 前缀标注）一并纳入。本 change 的头部识别 MUST 按该前缀**排除压缩自产的摘要消息**，使其不被提升进受保护头部完整保留区：它仍占据摘要槽位（仅 AR13 场景下按既有方式落在摘要槽，AR14 合入后由 AR14 提取其 `prev_summary` 折叠进新累积摘要）。否则该摘要消息会**既被头部完整保留、又被 AR14 折叠**，产生重复与冲突。

**为何**：把「完整保留范围」从「仅 system」扩展到「system + 初始意图」，是保护用户最初需求意图的最小且直接的手段；三层显式化也让后续 AR14（只摘中段新增）有清晰的中段边界可挂接。
**Alternatives**：①不改切分，只在摘要 prompt 里嘱咐 LLM「务必保留初始意图」——被否，摘要仍可能改写，保护不可靠；②把整段早期对话都完整保留——被否，违背压缩目的、无法回落到 `Tretained`。

### D2：初始意图消息的识别规则
初始意图消息定义为：会话开头处、位于任何 assistant / tool 消息之前的引导性 `user` 消息（即用户提出任务的最初一条或连续几条 user 消息）。识别规则：从 `conv_msgs`（非 system）开头起，连续的 `user` 消息纳入初始意图，遇到第一条非 `user` 消息即停止。保留条数有上界（**默认 2 条**，覆盖「一句引子 + 一句真正需求」的常见分句开场——尤以 IM 渠道用户爱拆句发为甚；上界经 pydantic `Settings` 字段 `compression_initial_intent_max` 动态可配置，可由 `.env` / `config/settings.yaml` 覆盖，亦可经 config dict / monkeypatch 注入，MUST NOT 引入全局可变状态）。

**为何**：初始意图几乎总是会话第一条（或开头连续几条）user 消息；以「开头连续 user 段」识别简单、可单测、无需 LLM 判断。上界防止异常长的开场独白把头部撑大到挤占 `Tretained`。
**Alternatives**：①用 LLM 判断哪条是意图——被否，引入额外 LLM 调用与不确定性，违背「规则可单测」；②保留全部 user 消息——被否，会让中段几乎无可压缩内容。
**已定（负责人确认）**：默认上界 = **2**，并经 `Settings.compression_initial_intent_max` 动态可配置。理由：开场「一句引子 + 一句真正需求」是真实人类习惯（IM 渠道分句发尤甚），上界 2 能把「真需求在第 2 条」的情形保住；多保 1 条头部增量极小，且 D3 投影 + 尾部收缩已兜住头部失控；再多（≥3）边际收益递减、头部风险上升，不取。

### D3：头部完整层计入 Tretained 固定投影
`_select_tail` 的 `fixed` 当前为 `estimate_tokens(system_msgs) + _SUMMARY_OVERHEAD_TOKENS`。本次改为 `estimate_tokens(head) + _SUMMARY_OVERHEAD_TOKENS`（head 含 system + 初始意图）。尾部规模仍以「投影 `<= target` 且 tool-pair 完整」选取；当头部本身已较大时，尾部会相应收缩，但尾部仍保 1 条下界与 tool-pair 完整（与 AR12 D3 一致的上界放宽）。

**为何**：初始意图是固定保留，必须计入投影，否则压缩后实际 token 会系统性超出 `Tretained`。
**Alternatives**：忽略头部增量、维持原 `fixed`——被否，会让目标线投影失真。

### D4：退化场景兜底
当会话过短，头部与尾部已覆盖全部对话消息、中段为空时：MUST NOT 生成空摘要消息（避免注入无信息的 `[Earlier conversation summary]\n`）。此时直接返回 `[*head, *tail]`（去重后按原顺序，不含摘要消息）。若头部与尾部存在重叠消息（同一条既属开头 user 又落入尾部），用 identity check 去重，保留单份、维持原顺序。

**为何**：空摘要既浪费一次 LLM 调用又污染上下文；短会话本就无需压缩中段。identity check 去重与 `_keep_tail` 的 `m is tail[0]` 口径一致（CLAUDE.md gotcha：内容相同的 dict `==` 相等但非同一对象，必须用 `is`）。
**Alternatives**：始终插入摘要消息——被否，空摘要无价值且可能被 AI 误读。

### D5：保持触发与目标线语义不变
`maybe_compress` / `compress_for_context_overflow` / `force` 入口、`Tmax` 触发判定、`Tretained` 目标线、阈值注入均不改；本 change 只改 `_compress` 内部切分与 `_select_tail` 的 `fixed` 口径。可观察的「何时触发压缩」行为与 AR12 等价。

**为何**：AR13 是切分改进，不是触发策略改进；隔离改动面，保 AR12 既有用例绿。

## Risks / Trade-offs

- [初始意图识别误判（开头不是 user，或开头 user 不是真正意图）] → 规则限定「开头连续 user 段 + 上界」，对非常规开场退化为「仅保留能识别到的开头 user」，最坏情况等同现状（无额外完整保留），不会比现状更差；加单测覆盖「开头非 user」「无 user」边界。
- [头部过大挤占 Tretained 致尾部过短] → 初始意图保留条数设上界（D2）；尾部保 1 条下界与 tool-pair 完整；目标线为「尽量回落」非「精确」（沿用 AR12 D3）。
- [头部与尾部重叠产生重复消息] → D4 用 identity check 去重，维持原顺序。
- [改 `_compress` 切分引入序列合法性回归] → 保留并扩展 AR12 既有 `test_context_mgr` 用例（尾部 tool-pair 完整、目标线回落）确保等价；新增三层顺序与去重断言。

## Open Questions

- 头部 token 占比超过 `Tretained` 的极端情形（初始意图本身就超目标线）下的退让策略——实现时确认是否仅保 system + 截断初始意图文本，spec 只约束「初始意图完整保留优先于目标线」。
