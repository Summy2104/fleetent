# Agent Loop 增强 — 执行决策日志

> 调研 + 规划批次（2026-06-07）。对照 hermes-agent / claude-code / openclaw / opencode 四个参考项目，对 fleetent 的 agent loop（`src/fleetent/runtime/`）做差距分析，甄别本轮实施范围。
> 本文档记录全盘规划、范围甄别、现状勘查结论、以及执行中遇到的问题与决策点，供审核（先文档后实施）。
> 与既有 `docs/skill-system-enhancements-decisions.md` 同范式。

---

## 0. 架构约束（不可逾越，甄别的前提）

| 约束 | 含义 |
|------|------|
| **agent ⊥ platform 解耦（硬规则）** | agent 必须能零依赖 platform 独立运行（`fleetent agent run`），唯一联系是 `agent.yaml` + `.env`。`runtime/` 不得 import `platform/`、不得调 platform 服务/API。验收口径："删掉整个 platform，这个 agent 还能跑吗？"= 必须 Yes。 |
| **OpenAI-compatible chat protocol** | 只走 `chat.completions`。Anthropic Messages 专属能力（thinking block 签名保留、`cache_control` ephemeral 断点）不直接适用。 |
| **禁 AI 框架** | 不引入 LangChain/LlamaIndex/LangGraph，也不把 tool-use 循环下放给等价框架（如 opencode 用 Vercel AI SDK）。手写循环保留。 |
| **asyncio** | 参考项目里 hermes 用 threading、opencode 用 Effect-TS；机制思路可借鉴，实现一律重写为 asyncio（fleetent 已有取消令牌树 + per-session `asyncio.Lock`）。 |
| **持久化走 store 边界** | 新增 per-session 运行态优先 **agent 侧兄弟文件**（`{sid}.pre-compact.json`/`.resume`/`.tool_outputs`/`.todo`，PR #163/#164 确立的约定），**不**写 session JSON `meta`（D10：重写整个 JSON + 刷 mtime），**绝不**写 platform `session_meta` 表（runtime→platform 反向依赖，PR #163 已回退）；DB 必走统一 runtime + named params + Alembic。兄弟文件**原子写、不取 `session_lock`**（IM 整 run 持锁，运行中再取会死锁）。 |
| **流程** | 每改进 = 一个 OpenSpec change（propose→apply→archive）+ 一个 PR（bb-pr → main）；每 task 严格 TDD 红绿；新配置项进 `agent.yaml`（经 `GovernanceConfig`/`AgentFile`），不进 platform `settings.yaml`。 |

**甄别原则**（沿用 skill 批次）：① 明确价值 + 低风险 → 做；② 高风险/违反原则 → 不做（记理由）；③ 大特性/跨模块/协议受限/需依赖讨论 → 暂缓（记理由）。

---

## 1. 跨项目差距综合（agent loop 维度）

fleetent 现状基线（AR 系列已实现）：双维度预算(turns+tokens)+Grace Call、并行工具三阶段分发+同容器串行、循环检测(arg 指纹**+ 结果哈希无进展**)、重复护栏、上下文压缩(阈值+anti-flap+分层+增量摘要)、消息卫生、错误分类+多目标模型回退+健康熔断、prompt-cache 前缀排序、多模态 vision、长期上下文(KB+记忆)注入、子 agent(深度1并行)、人工审批门、可观测 trace、MCP 降级、skills read-on-demand。

| 缺口/机制 | hermes | openclaw | opencode | claude-code | fleetent 现状 | 甄别 |
|---|:--:|:--:|:--:|:--:|---|:--:|
| **运行中转向 steering** | ✓ | ✓ | ✓ | ~ | **无**（仅 cancellation） | **做 C1** |
| **一等 Todo/Plan（持久化+状态机）** | ✓ | ✓ | ✓ | ✓ | **半成品**（内存版 todo，不持久） | **做 C2** |
| **结构化压缩摘要 + 续跑契约** | ✓ | ✓ | ✓ | ✓ | 缺（摘要为英文自由文本） | **做 C3a** |
| **老工具结果跨轮 prune** | – | – | ✓ | ~ | 无（仅单条截断） | **做 C3a** |
| **按模型上下文窗口预算 + overflow 处理** | ✓ | ✓ | ✓ | ✓ | 缺（无 context_window，骨架零接线） | **做 C3b** |
| **同模型退避重试（尊重 Retry-After）** | ✓ | (SDK) | ✓ | – | 缺（`should_retry` flag 未消费） | 可选 T2 |
| **planning-only/空回复自纠错** | – | ✓ | – | – | 无 | 可选 T2 |
| no-progress 循环检测（结果哈希） | – | ✓ | ✓ | – | **已实现**（Signal B） | 已有，跳过 |
| Hooks 扩展体系 | ✓ | ✓ | ✓ | ✓ | 无 | 暂缓 |
| 权限 ruleset（allow/deny/ask+反馈+持久化） | ~ | ✓ | ✓ | ✓ | 部分（白名单+审批门） | 暂缓 |
| Plan Mode 只读规划态 | – | – | ✓ | ✓ | 无 | 暂缓 |
| reasoning/thinking effort 透传+保留 | ✓ | ✓ | ✓ | ✓ | 无 | 暂缓 |
| 崩溃续跑 / aborted-run resume | – | ✓ | – | – | 无 | 暂缓 |
| 不可信工具结果包裹（注入防御） | ✓ | – | – | – | 无 | 暂缓 |
| Checkpoint/Revert 文件时间旅行 | – | ~ | ✓ | – | 无 | 暂缓 |
| LLM 智能审批放行误报 | ✓ | – | – | – | 无 | 不做 |

> 证据：四份完整调研报告（含 file:line）见会话记录；可按需补落 `docs/archive/internals/reference-survey-{opencode,claude-code}.md`（hermes/openclaw 已有 survey）。

---

## 2. fleetent 现状勘查结论（落点核准，影响设计）

1. **steering 并发模型**：IM 路径 `im_gateway/normalizer.py:156-222` 在 `session_lock` 内包住 `load→run→save`（**整 run 持锁**）→ 同会话第二条消息阻塞在锁上、串成下一 turn（隐式 queue，但无反馈/去抖/可控）。`run()` 用 `messages[:]=`（loop.py:1268-1275）改 caller 的 list（可触达但裸 append 有竞态）；`run_stream()` 的 messages 是函数内部对象且 rebind（loop.py:1539/1620）→ **对外不可见**，且 **run_stream 当前完全不落库**。`/chat`+`/ws` 已迁到 `runtime/agent_app.py:338-401`；**全仓无 per-session 活跃 run 登记表**；IM 路径调 run **不传 cancel_token**（interrupt 无抓手）。TUI `tui/dispatch.py` 有 per-run_id 的 token 表 + `METHOD_ABORT`（现成 interrupt 雏形）。
2. **Todo 已存在但极简**：`tools/interaction_tools.py:47-86` 有内置 `todo(set/get/clear)`，但用**进程内模块级 dict**、不持久、无状态机、压缩会丢、违反"禁全局可变状态"精神。
3. **压缩**：`_build_summary_prompt`(context.py:479-491) 为英文自由文本、无"未完成任务/续跑"语义；`compress_for_context_overflow`(154-179) 与 `error_classifier` 的 `should_compress/should_retry`(87-89) **定义了但零接线**（loop 只消费 `should_switch_model`）；anti-flap(658-713) 仅护 auto 路径。
4. **模型上下文窗口**：**fleetent 任何地方都没记录"模型 context window"**——所有 `max_tokens` 都是输出上限；`context_max_tokens`(agent_config.py:222, 默认 200k) 只是压缩阈值分母，**不与具体模型绑定**（切到小窗口 fallback 模型会压不动就撞 400）。需给 `ModelTarget` 加 `context_window`（进 agent.yaml）。
5. **loop_detector**：`loop_detector.py:123-133` **已同时用 arg 指纹(Signal A) + 结果哈希(Signal B 无进展)** → no-progress 检测无需再做。
6. **session 结构**：`session/manager.py` 为 `{meta, messages}` 信封，原子写(tmp→rename)+`session_lock` 已具备 → per-session 运行态用 **兄弟文件**（`.pre-compact.json`/`.resume`/`.tool_outputs`，PR #163/#164 确立），**不**用 `meta`（D10：写 meta 重写整个 JSON+刷 mtime）；todo 走 `{session_id}.todo`。`ToolContext`(registry.py:21-35) 已带 `session_id`；`@tool` 支持 `self_truncates` 等旁路 metadata（可仿造 `prune_exempt`）。

---

## 3. 决定执行（本批次）

| 编号 | 方向 | 拟 change 名 | 预计 PR | 解耦合规 |
|------|------|-------------|:---:|:---:|
| **C1** | 运行中转向 steering | `agent-input-steering`（含 run_stream 落库前置） | 1 | ✅ 纯 agent 侧 |
| **C2** | 一等 Todo/Plan 持久化+状态机 | `agent-task-tracking`（MODIFY `builtin-interaction-tools`） | 1 | ✅ session-local |
| **C3a** | 压缩摘要质量：结构化模板+续跑契约+工具结果 prune | `compression-continuation-summary` | 1 | ✅ 纯 runtime |
| **C3b** | 按模型窗口预算 + overflow 处理 + 压缩后守卫 | `compression-context-window-budget` | 1 | ✅ 配置进 agent.yaml |
| **C4** | reasoning/thinking 透传 + 跨轮保留（选性纳入） | `agent-reasoning-passthrough` | 1 | ✅ 后端不支持则降级 |

> 压缩拆成 C3a/C3b 两个 change/PR：C3a 是"摘要质量"内聚簇（纯 prompt/重排，低风险），C3b 是"溢出安全"内聚簇（需新增 `context_window` 配置 + 接线 overflow 骨架）。可独立 review、独立回滚。✅ 审核确认：拆成 2 个 PR。

### C1 — 运行中转向 steering

- **问题**：IM(Slack/Telegram) 多轮异步场景，用户在 agent 长跑工具循环时想补一句/换方向/打断，现状只能干等（隐式 queue 无反馈）或取消重来。
- **方案**（纯 agent 侧）：
  - 新增 `runtime/steering.py`：per-session 活跃 run 登记表 `_active: dict[session_id, RunHandle]`（`RunHandle` 持 `cancel_token` + `pending: asyncio.Queue[str]` + mode）；API `register_run`(asynccontextmanager) / `steer` / `interrupt` / `is_running`；Queue `maxsize`(上限) + 去抖窗口合并。遵守"全局可变状态可 monkeypatch 注入 + reset"红线（仿 `session/manager._locks`）。
  - `runtime/loop.py`：run()/run_stream() 入口 `register_run`（贴 `_active_runs` 处 1110/1138）；主循环**在 compress 之后、sanitize 之前**插 `_drain_pending`（run 1275→1280；run_stream 1622→1626），把 pending 文本逐条 `append({"role":"user",...})`。轮间检查点 append → 天然规避并发竞态 + 不破坏 tool_call/tool_result 配对。
  - `im_gateway/normalizer.py`：`route()` **在抢 session_lock 之前**先 `steering.is_running()` 分派 steer/interrupt/queue；run 调用包 `register_run` 并传 `cancel_token`。queue 模式补"排队中"反馈。
  - `tui/dispatch.py`+`protocol.py`：新增 `METHOD_STEER`（投 pending），登记统一到 steering；interrupt 复用 `METHOD_ABORT`。
  - **前置子项**：run_stream 收尾补 `session_mgr.save`（现状不落库，否则流式路径 steer 注入会丢）。
- **agent.yaml 配置**（`AgentFile` + `GovernanceConfig` + `_governance_from_file`）：`steering_mode: queue|steer|interrupt = queue`、`steering_debounce_seconds: float = 0`、`steering_max_pending: int = 8`。**默认 `queue`**（最接近现状，零行为惊吓），steer 为显式 opt-in。
- **测试**：steering.py 单测（注册/注入/去抖/上限/interrupt）；loop drain 注入点单测（注入后序列经 sanitize 合法、不被压缩吞）；normalizer 分派单测（运行中 steer 不抢锁、queue 串行有反馈）。
- **风险**：见 §8（IM steer 与 session_lock 张力、message 契约、流式 vs 阻塞持久化差异、interrupt 半途语义、TUI 同 session 并发）。**本批次最大/最高风险项**。

### C2 — 一等 Todo/Plan 持久化 + 状态机

- **问题**：现内存版 todo 重启即丢、无"进行中/已完成"状态、压缩后模型"忘记"已做步骤；长任务（企业工单）易漏步。
- **方案**（纯 agent-local，零 DB 新表，对齐 PR #164 兄弟文件约定）：升级 `tools/interaction_tools.py` 的 todo 工具——条目带状态机 `[{id, text, status}]`（单 `in_progress` 约束，仿 openclaw `update_plan`/CC `TodoWrite`）；权威状态存 **agent 侧兄弟文件 `{session_id}.todo`**（JSON 内容；与 `.pre-compact.json`/`.resume` 同模式，**不用** session.meta——D10 已否决：写 meta 要重写整个 session JSON + 刷新 mtime）。`session/manager.py` 新增 `read_todo`/`write_todo`(原子 tmp→rename)/`clear_todo` 并导出，`cleanup_expired` 连带删 `.todo`。**关键：原子写、不取 `session_lock`**（IM 整 run 持锁，工具内再取会死锁；与 `write_compaction_checkpoint`/`mark_resume_pending` 同为 lock-free 原子写）。废弃模块级 `_todo_store`。可选叠加"从历史最近 todo 响应 hydrate"作兜底。
- **与 C3a 协同**：未完成 todo 由 C3a 的"逐字保留块"在压缩后注入上下文（数据源 `.todo` 文件），保证压缩后仍可见。两者解耦：C2 先落地（持久化本身即增值），C3a 再消费。
- **agent.yaml 配置**：可选 `todo_max_items`（防 meta 膨胀）。
- **测试**：set/get/update/complete 状态机单测；session.meta 持久化往返（integration，真实 session 文件）；单 in_progress 约束；子 agent 默认禁写主清单（参考 opencode）。
- **风险**：meta 全量写盘需保持 todo 精简；hydrate 兜底解析脆弱（次级路径）。

### C3a — 压缩摘要质量：结构化 + 续跑契约 + 工具结果 prune

- **问题**：摘要为自由文本、丢工具轨迹、无"未完成任务逐字保留"，长任务压缩后易丢目标；老工具结果占满 token 无回收。
- **方案**（纯 runtime，无新依赖）：
  - 结构化模板：改 `_build_summary_prompt`(479-491) 为分节（目标/已完成/进行中/未完成/相关文件/下一步），并在 `_summarize` 喂入时补摘工具调用轨迹（现仅喂 user/assistant，458-459）。
  - 续跑契约：`_compress`(255-364) 在 head 与 summary 间新增"逐字保留的 active-task 块"（最近未完成用户请求逐字 + `meta["todo"]` 未完成项），用"single constant 驱动多处"模式新增前缀常量；注意保持 `_keep_tail`/head id 去重的 identity 不变式（context.py:616-626/278-280）。
  - 工具结果 prune：`@tool` 新增 `prune_exempt` 维度（仿 `self_truncates` 46/98-99/130-132），给 `read_skill` 等打豁免；`_pre_cleanup`(494-502) 新增 `_prune_stale_tool_results` pass，把 middle 段非豁免、非最近 N 次的 tool 结果替换占位（复用 `_dedup_tool_calls` 的"丢 caller 同丢 orphan result"范式 566-574）。
- **测试**：结构化摘要包含 active-task 逐字段；prune 保留豁免工具 + 配对有效；identity 不变式不破。
- **风险**：摘要含工具轨迹会增 token；active-task 块需计入 tail floor 预算。

### C3b — 按模型上下文窗口预算 + overflow 处理 + 压缩后守卫

- **问题**：压缩阈值基于 agent 自填常量、与真实模型脱节；`compress_for_context_overflow` 与 `should_compress` 骨架零接线 → 撞 400 `context_length_exceeded` 直接 `raise`，无"压缩后重试"。
- **方案**：
  - 新增 `ModelTarget.context_window: int | None`（agent_config.py:84-113）→ agent.yaml `models.targets[].context_window`；平行透传 `ModelTargetSnapshot`/`ResolvedModelConfig`/`_merge`(resolver.py:36-49/62-77/154-173)。`context_max_tokens` 退化为未配窗口时的回退默认（向后兼容）。
  - 发送前预算：调 LLM 前按"`context_window` − 预留输出 − 安全余量"判定，不足 → `compress_for_context_overflow` → 仍不足 → 按工具结果 truncate（compact/truncate 路由）。
  - 事后兜底：`_call_policy_chat`/`_stream_policy_chat` except 新增分支——`classify(exc).should_compress` → 压缩 → retry 同 target（区别于 `should_switch_model`），接线现成 flag。
  - 压缩后守卫：复用 anti-flap 的 savings 度量(700-702)给 force/overflow 路径加"重试上限 + 无正 savings 即放弃"，防"压不下去→无限 retry"。
- **测试**：context_window 配置解析+透传；预算路由（compact vs truncate）；overflow→compress→retry 一次成功 / 守卫触发放弃；无窗口配置回退兼容。
- **风险**：overflow 不得触发 switch_model（table 已正确 `should_switch_model=False`）；守卫上限必须存在。

### C4 — reasoning/thinking 透传 + 跨轮保留（本轮选性纳入）

- **问题**：fleetent 不向模型请求 reasoning，也不保留 `reasoning_content`；对支持推理的自托管模型（DeepSeek-R1/QwQ via vLLM 等）无法利用其推理质量。
- **方案**（OpenAI-compatible、后端不支持时零副作用）：
  - `model/resolver`：按 task_type/target 注入 reasoning 参数（`reasoning_effort` 或 `extra_body.reasoning`），经 agent.yaml `models.targets[].reasoning`/route 配置；未配置则字节级不变。
  - `runtime/loop.py`：消费流式/非流式响应中的 `reasoning_content`（若有），流式加 `reasoning_delta` 事件，并按需保留在 assistant 消息里供跨轮。
  - `runtime/context.py`：压缩时的 reasoning 保留策略（默认丢旧 reasoning、保留最近一轮，避免膨胀）。
- **agent.yaml 配置**：`models.targets[].reasoning: {effort: low|medium|high}`（可选）。
- **解耦**：纯 agent 侧；后端不支持时优雅降级（不报错、不变行为）。
- **测试**：reasoning 参数注入（配置在/不在）；reasoning_content 消费+保留+压缩策略；后端无 reasoning 时无副作用。
- **风险**：各家 OpenAI-compatible 后端 reasoning 字段不统一，resolver 需映射 + 容错；Anthropic thinking 签名保留不在范围（协议受限）。

---

## 4. Tier-2（低风险，✅ 审核确认：做完本轮紧接着做）

| 编号 | 项 | 落点 | 说明 |
|------|----|------|------|
| T2-1 | 同模型退避重试（尊重 Retry-After，5xx 必重试，与切模型分离） | `error_classifier`(已有 `should_retry` flag 未消费) + loop 重试路径 | on-prem fallback 目标少时尤其值；瞬时 429/503/timeout 退避重试同模型优于立刻切次优模型 |
| T2-2 | planning-only/空回复自纠错（光说不做→注入 act-now 重跑，带上限） | loop 主循环 + termination | 显著提升 on-prem 开源弱模型在 agentic 任务的完成率 |

> no-progress 循环检测**已实现**（§2.5），不列入。

---

## 5. 暂缓（记理由，不在本轮）

| 项 | 暂缓理由 |
|----|---------|
| **Hooks 扩展体系**（pre/post tool-use、输出变换） | 大特性，跨 `tools/registry`+`governance`+`config`；战略价值高（企业 on-prem 定制不改核心）。须 agent-local（hook 配置进 agent.yaml、脚本 agent-local）。单独立项设计。 |
| **权限 ruleset 升级**（allow/deny/ask + 拒绝带反馈 + always 持久化） | 越界到 `governance/`（agent_policy + permission_gate 重构）；reject-feedback 很好但属治理域。单独立项。 |
| **Plan Mode 只读规划态** | 跨模块（agent 定义 + 权限只读护栏 + loop 注入 + plan_exit 审批切换）。依赖权限 ruleset，宜在其后。 |
| reasoning/thinking 透传 | **已纳入本轮（C4）** —— 审核决定纳入，见 §3 C4。Anthropic thinking 签名保留仍不在范围（协议受限）。 |
| **不可信工具结果包裹**（`<untrusted_tool_result>` 间接注入防御） | 小而有价值（安全向），但属安全专题；建议与其它安全增强(tool-arg-secret-redaction 等)合并单独立项。 |
| ~~崩溃续跑 / aborted-run resume~~ → **已完成** | ✅ PR #164 `session-resume-agent-side` 已落地（agent 侧 `.resume` 标记文件）；从计划移除。 |
| **Checkpoint/Revert 文件时间旅行** | 偏代码 agent；依赖工作区可快照(git/sandbox)，与 fleetent IM 定位弱相关。 |

---

## 6. 不做（记理由）

| 项 | 不做理由 |
|----|---------|
| **把 tool-use 循环下放给框架**（opencode 的 Vercel AI SDK 模式） | 违反"禁 AI 框架"。fleetent 手写循环保留，只借鉴机制语义。 |
| **LLM 智能审批自动放行高危命令**（hermes `_smart_approve`） | 安全立场冲突：让 LLM 判定放行高危操作扩大攻击面，on-prem 数据主权平台尤敏感。high 风险必走人工审批门。（若未来需要，仅作 medium 档可选加速器，单独评估。） |
| **硬依赖 `cache_control` ephemeral 断点** | Anthropic Messages 专属；chat.completions + 多数自托管后端不支持。现有"稳定 system 前缀排序"已是协议内最优；不硬接 cache_control。 |

---

## 7. 执行顺序 & 依赖

建议顺序（每项独立 change+PR，bb-pr → main；多项都可能动 `loop.py`/`context.py`，**串行执行避免合并冲突**）：

```
C2 (todo 持久化, 最小, 验证 OpenSpec→TDD→bb-pr 全流程)
  → C3a (压缩摘要质量, 消费 C2 的 meta.todo)
  → C3b (窗口预算+overflow)
  → C1 (steering, 默认 steer, 含 run_stream 流式落库子任务)
  → C4 (reasoning/thinking 透传, 含压缩侧保留)
  →（本轮后紧接）T2-1 (退避重试) → T2-2 (planning-only 自纠错)
```

依赖：C3a 的 active-task 块可消费 C2 的 `meta["todo"]`（弱依赖，C3a 也能独立先做"逐字保留最近用户请求"）。C1 的 run_stream 落库前置与 C3b 无冲突。

---

## 8. 关键风险

- **C1 IM steer 与 session_lock 张力**：steer/interrupt 必须在抢 `session_lock` **之前**走 steering 分支并 return，否则卡锁退化成 queue（normalizer 改造最易错点）。
- **C1 message 契约**：注入只能在轮间检查点（compress 后、sanitize 前），**绝不在工具调用半途**插 user 消息，否则 `MessageContractError` 终止 run。
- **C1 流式持久化**：run_stream 当前不落库；steer 注入需补 save，否则流式路径注入丢失。
- **C1 interrupt 半途语义**：CancelToken 在轮间/工具 await 检查点才生效，非硬中断；UI 需"停止中"反馈。
- **C3b overflow 重试**：必须自带重试上限 + savings 守卫，且不触发 switch_model。
- **通用**：所有新全局可变状态（steering 登记表）须可 monkeypatch 注入 + reset；所有新配置默认值须镜像现状（零行为惊吓）；`ruff format` 只格式化改动文件，避免污染 diff。

---

## 9. 决策结果（审核确认 2026-06-07）

| # | 决策 |
|---|------|
| 1 范围 | ✅ 认可。本轮 = C2 + C3a + C3b + C1 + **C4（reasoning/thinking 透传）**；压缩拆 C3a/C3b 两个 PR。 |
| 2 Tier-2 | ✅ 纳入，**做完本轮紧接着做**（T2-1 退避重试 → T2-2 planning-only 自纠错）。 |
| 3 选性纳入 | ✅ reasoning/thinking 透传纳入本轮（C4）；设计为后端不支持时优雅降级、零副作用。其余跨模块项（Hooks/权限 ruleset/Plan Mode/崩溃续跑/不可信结果包裹/Checkpoint）维持暂缓。 |
| 4 steering 默认模式 | ✅ **IM 默认 `steer`**（不再 queue）；queue/interrupt 仍可经 agent.yaml 配置。默认路径须稳——去抖/上限/反馈做扎实。 |
| 5 执行顺序 | ✅ C2 → C3a → C3b → C1 → C4 →（紧接）T2-1 → T2-2。串行。 |
| 6 run_stream 落库 | **并入 C1**（我的建议）：IM 路径 `run()` 天然落库、默认 steer 即生效；run_stream 落库仅流式(TUI/SSE)路径需要，作为 C1 子任务。若实施中发现是更广的独立缺口（TUI 历史完全不持久），再拆为 C1 前一个小 change。 |

---

## 10. 执行记录（实施期间追加）

> 每个 change 实施中遇到的问题/决策、偏离本规划之处、实际改动点，在此追加。

### 2026-06-07 — 拉取 main 后的范围/设计修正（PR #163/#164）

实施前 `git pull origin main` 带回两个刚归档的解耦返工：
- **PR #163 `revert-session-meta-runtime-coupling`**：回退 token/compaction 往 platform `session_meta` 表写 agent 运行时数据（runtime→platform 反向依赖）。
- **PR #164 `session-resume-agent-side`**：`resume_pending` 迁到 agent 侧 `.resume` 兄弟标记文件；至此 `runtime`/`session`/`im_gateway` 不再 import `platform.chat_management`，agent 可真正独立运行。

**对本批次的决策影响**：
1. **C2 改设计**：todo 持久化从 `session.meta` → **agent 侧兄弟文件 `{sid}.todo`**（对齐 `.resume`/`.pre-compact.json`；设计文档 D10 已否决用 meta：重写整个 JSON + 刷 mtime）。**原子写、不取 `session_lock`**——IM 整 run 持锁，工具内再取会死锁（证据：`write_compaction_checkpoint`/`mark_resume_pending` 同为 lock-free 原子写）。
2. **移除「崩溃续跑/aborted resume」**：已由 PR #164 完成（原列在暂缓 §5）。
3. **约束强化**：本批次所有改动严禁 runtime→platform 依赖、严禁写 platform `session_meta` 表；per-session 运行态一律走 agent 侧兄弟文件。

### 2026-06-07 — C2 `agent-task-tracking` 完成

- **实现**：todo 工具升级为 `set`/`update`/`get`/`clear` 状态机（条目 `{id,text,status}`、单 `in_progress`、`update` 拒绝第二个 `in_progress`）；权威状态存 agent 侧 `{sid}.todo`（JSON、lock-free 原子写）；`session/manager.py` 加 `read_todo`/`write_todo`/`clear_todo` + 导出 + `cleanup_expired` 连带删 `.todo`；废弃 `_todo_store`；无 session 降级为 `_ephemeral_todo`（仅此 fallback 保留进程内态）。
- **决策**：`.todo` 后缀不带 `.json`（避开 `rglob("*.json")` 误判，仿 `.resume`）；穷举 Literal 的 `todo` 用 `assert_never(action)` 收尾（解决 mypy unreachable）。
- **测试**：`tests/unit/test_session_todo_store.py`(9) + `test_interaction_tools.py` todo 段重写（含持锁不死锁回归）；全量 **3719 passed, 14 skipped**；mypy / ruff（改动文件）/ openspec validate --strict 均通过。
- **既有漂移观察（非本 change，未修，避免污染 diff）**：`check_test_layers` 报 `tests/unit/test_config.py:166`（commit `e1762706` 引入）；`ruff check src tests` 报 `src/fleetent/tools/file_tools.py`(9) 与 `tests/unit/test_session_resume_marker.py`(1) unused import。建议另起 `chore` 清理。CI 门禁（`make test-unit-ci`/`test-integration`）不含 check_test_layers，故不阻塞本 PR。

### 2026-06-07 — C3a `compression-continuation-summary` 完成

- **范围微调（实施期决定）**：把**工具结果 prune** 从 C3a 挪到 **C3b**——prune 是"token 回收"，与 C3b 的"按窗口预算"主题更内聚；C3a 专注摘要质量，更小更聚焦。C3a = 结构化摘要模板 + active-task 续跑块。
- **实现**：`_build_summary_prompt` 重写为结构化模板（Goal/Completed/In Progress·Pending/Key Findings/Next Steps，首次与增量两分支同结构，要求逐字保留未完成工作+下一步）；新增 `_active_task_block(session_id)` 读 C2 的 `.todo` 未完成项，作为逐字 system 块在 summarized/degraded 路径注入 `[head, active-task, summary, tail]`（no_middle 不注入）；`_select_tail` 增 `extra_fixed` 把 active 块 token 计入投影。无 session / 无未完成 / 读失败安全退化。
- **决策**：active 块用新建 dict，不入 head/tail identity 集合，不破坏既有去重；prompt 保持英文（跨模型稳健）。
- **测试**：`tests/unit/test_compression_continuation.py`(6)；全量 **3725 passed, 14 skipped**；mypy / ruff（改动文件）/ openspec validate --strict 通过；既有压缩测试无回归（无 session 调用行为不变）。
