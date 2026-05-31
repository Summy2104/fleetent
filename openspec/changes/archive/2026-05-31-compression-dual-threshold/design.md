## Context

`context_mgr.maybe_compress`（context_mgr.py 行 25-51）当前用单一阈值判触发：`threshold = int(cfg["max_tokens"] * cfg["compress_threshold"])`，超过即压缩；压缩动作把 `to_summarize` 段交给 `_summarize`（调 LLM）生成一条摘要 system 消息，尾部 `keep_recent` 条经 `_keep_tail` 保留（含 tool-pair 完整性 identity check）。压缩后的体量由「保留多少尾部」隐式决定，没有显式目标线。

现状只有一个隐式触发路径：调用方在每轮 LLM 调用前调 `maybe_compress`，越过阈值才压缩。没有手动触发入口，也没有「LLM 报上下文过长」时的补救入口。

本 change 属 v1.0 agent-runtime「上下文压缩增强 / 双阈值触发（AR12）」。配置机制沿用 pydantic-settings 读 env（`Settings`），阈值经 `context_mgr._default_config()` 惰性读取（同既有模式）。

约束（CLAUDE.md）：禁止 AI 框架；禁止 ORM；禁止全局可变状态（阈值必须可经 config dict / monkeypatch 注入）；新模块结构 import → 常量 → 数据类 → 函数；mypy strict；行长 100；TDD Hard Gate；LLM 调用单测必须 mock（`patch get_client_and_config`）。

## Goals / Non-Goals

**Goals:**
- 用 `Tmax`（触发）与 `Tretained`（目标）双阈值替代单一 `compress_threshold`。
- 压缩后估算 token 回落到 `max_tokens * Tretained` 附近或以下。
- 强制 `Tretained < Tmax` 并保持间距，避免压缩后立即再次越线。
- 两阈值支持部署级配置（`Settings` env 字段）+ config dict 注入覆盖。
- 提供手动触发入口（`/compact` 语义）：无条件压缩到 `Tretained`。
- 提供「LLM 上下文过长」错误触发入口：可请求压缩后由调用方重试。
- 保持 `maybe_compress` 的既有 config 注入契约与尾部 tool-pair 完整性行为。

**Non-Goals:**
- 不实现分层保留改进（保护初始意图）——独立 change（AR 同节其它 [ ] 项）。
- 不实现持久化增量摘要、压缩前轻量清理、压缩可追溯、压缩反抖动——各自后续 change。
- 不在本 change 内接线 agent_loop 的 `/compact` 用户命令解析与错误重试编排——本次只提供 context_mgr 侧的触发 API，命令/错误的端到端接线属调用方（后续 change）。
- 不引入新依赖；不改 `_summarize` 的 LLM 调用方式与 `_keep_tail` 的 identity check 算法。

## Decisions

### D1：双阈值语义与解析

`Tmax` = 触发比例，`Tretained` = 目标比例，二者均相对 `max_tokens`：
- 触发判定：`estimate_tokens(messages) > max_tokens * Tmax` 时压缩（严格大于，与现状 `<= threshold` 直接返回的边界一致）。
- 压缩目标：压缩后 `estimate_tokens` 应 `<= max_tokens * Tretained`（目标线；受 tool-pair 完整性约束可能略高，见 D3）。

`_default_config()` 返回 dict 增加 `tmax_ratio` / `tretained_ratio` 两键（替代 `compress_threshold` 的触发角色）。

**为何**：触发与目标解耦后，压缩体量可控且可与触发线拉开间距。
**Alternatives**：①保留单阈值、压缩固定保留 N 条——被否，现状即如此，体量不可控、无法抑制频繁压缩；②用绝对 token 数而非比例——被否，与既有 `compress_threshold` 比例风格不一致，且 `max_tokens` 变化时需同步两个绝对值。

### D2：`Tretained < Tmax` 间距约束

强制 `Tretained < Tmax`；二者默认值取 `Tretained=0.6` / `Tmax=0.8`，留出 20% `max_tokens` 的间距，使压缩后至少能再容纳相当量新消息才会再次触发。若注入的 config 违反 `Tretained < Tmax`，按显式校验处理（实现时决定是钳制还是报错，spec 只约束「必须保持 `Tretained < Tmax`」）。

**为何**：间距是抑制频繁压缩、保护 prompt 缓存的核心手段；spec 场景对此显式验收。
**Alternatives**：固定间距常量（如恒定 0.2）——被否，不够灵活，部署可能希望不同上限/目标组合。

### D3：压缩目标线如何达成（与 tool-pair 完整性的关系）

压缩通过「摘要前缀 + 保留尾部」实现回落。为命中 `Tretained` 目标，压缩逻辑以目标线为准选择保留的尾部规模，而非固定 `keep_recent`；但 `_keep_tail` 的 tool-pair 完整性（不在 tool_call 中间截断、identity check）优先级更高，因此压缩后实际 token 可能略高于 `Tretained`，这是可接受的上界放宽。

**为何**：消息契约完整性不可妥协（否则 LLM 报错），目标线是「尽量回落到」而非「精确等于」。
**Alternatives**：严格裁到目标线、容忍截断 tool-pair——被否，会产生残缺消息序列使 LLM 报错。
**Open**：保留尾部规模的选取策略（仍以 `keep_recent` 为下界、按目标线动态扩/缩，还是纯按目标线反推）在实现首步用现有 `test_context_mgr` 核实后定。

### D4：显式触发入口

提供独立于「是否越过 `Tmax`」的压缩入口：
- 手动触发（`/compact` 语义）：调用方传入「强制压缩」意图时，无视当前是否越过 `Tmax`，直接压缩到 `Tretained`。
- 上下文过长错误触发：当 LLM 返回上下文过长类错误，调用方可请求一次压缩；context_mgr 提供该入口，端到端「捕获错误 → 压缩 → 重试」的编排由调用方负责（Non-Goal）。

实现形态（新增 `force` 参数 vs 新增独立函数）在实现时定；spec 只约束行为。

**为何**：AR12 明确要求手动触发与错误触发两个入口；自动触发已由现状路径覆盖。
**Alternatives**：仅自动触发——被否，不满足 AR12 验收。

### D5：移除 `context_compress_threshold`，由 `context_tmax_ratio` 取代

现状 `Settings.context_compress_threshold: float = 0.8` 与 `_default_config` 的 `compress_threshold` 键，本次**移除**；触发角色由新增的 `context_tmax_ratio`（默认 0.8，语义等价）承担。`_default_config` 不再返回 `compress_threshold` 键，改返回 `tmax_ratio` / `tretained_ratio`。

**为何**：单一事实来源、避免两个字段管同一件事的混淆；项目 pre-1.0 且为内部能力，重命名可接受。
**迁移**：若部署 `.env` 曾设 `CONTEXT_COMPRESS_THRESHOLD`，改为 `CONTEXT_TMAX_RATIO`（默认值一致 0.8，不设则用默认）；在 PR / 变更说明中提示。
**Alternatives**：保留旧字段作兼容来源——被否（决定移除），两字段并存增加文档与优先级负担。

## Risks / Trade-offs

- [`Tretained` 过低导致单次压缩丢失过多上下文] → 默认 0.6 为中性目标；可经 env / config 注入调高；tool-pair 完整性保证不产生残缺。
- [`Tmax` 与 `Tretained` 间距过小仍频繁压缩] → spec 强制 `Tretained < Tmax` 且默认留 0.2 间距；配置校验防误配。
- [压缩后实际 token 因 tool-pair 完整性超过 `Tretained`] → 接受为上界放宽（D3）；目标线语义为「尽量回落」非「精确」。
- [移除 `context_compress_threshold` 破坏既有部署 env] → D5 迁移说明（改用 `CONTEXT_TMAX_RATIO`，默认值一致）；项目 pre-1.0 内部能力，影响可控；tasks 覆盖「旧字段已移除、新字段生效」回归。
- [手动 / 错误触发入口未在调用方接线被误认为已端到端可用] → Non-Goals 明确本次只提供 context_mgr 侧 API，命令/错误编排属后续 change。

## Open Questions

- 保留尾部规模的目标线达成策略（D3 Open）——实现首步核实后定。
