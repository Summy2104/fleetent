## Context

`model_router.py` 是 agent_loop 与底层 provider 之间唯一的中间层：`RouteConfig`（frozen dataclass，含 `base_url` / `model` / `api_key_env` / `max_tokens` / `fallbacks`）由 `ROUTES` 表按 `task_type` 提供，`get_(async_)client_and_config` 返回 `(client, cfg)`。`agent_loop.py` 的 `_call_with_fallback`（行 74）与 `_stream_with_fallback`（行 102）是仅有的两个 `client.chat.completions.create()` 调用点，二者当前只传 `model` / `messages` / `tools` / `max_tokens`（stream 版另加 `stream` / `stream_options`），temperature / top_p 等采样参数全部沿用 provider 默认。

本 change **依赖 `request-routing-override`（MR1）并排在其后**。MR1 已落地三样基础设施，本 change 在其上扩展，不重建：
- `RouteOverride`（frozen dataclass，字段全可选）——本次为其新增 `params` 字段。
- `_apply_override(cfg, override) -> RouteConfig`（单一私有纯函数，sync/async 两入口共用）——本次为其新增 `params` 深合并分支。
- `get_(async_)client_and_config(..., override=None)` 入口——本次无需再改，沿用 MR1 已加的 `override` 通道。

本 change 是 docs/capabilities/model-router.md「规划中（v1.0）」的 `按 task_type 配置采样参数`，也是后续模型选型/质量调优的地基。首要目标是把采样参数维度接成对调用方零侵入（不填即现状），且不破坏 router「无状态、config 驱动、OpenAI-compatible SDK」三条原则。

约束（CLAUDE.md）：禁止 AI 框架；禁止 ORM；禁止全局可变状态；router 用 OpenAI-compatible SDK 且 config 驱动；mypy strict；行长 100；TDD Hard Gate；测试 mock LLM，不发真实请求。

## Goals / Non-Goals

**Goals:**
- 在 `RouteConfig` 引入 `params: dict[str, Any]`，承载 per task_type 默认采样参数。
- 在 MR1 的 `RouteOverride` 引入 `params: dict[str, Any]`，承载单次调用采样参数覆盖。
- 在 MR1 的 `_apply_override` 实现 `params` 深合并：override 键替换、未覆盖键沿用 base。
- `_call_with_fallback` / `_stream_with_fallback` 把 effective `params` 经 `**cfg.params` 透传给 `create()`。
- `max_tokens` 保持一等字段，不并入 `params`。
- 优先级固定：调用覆盖 params > task_type params > provider 默认（不传即默认）。

**Non-Goals:**
- 不做 `ROUTES` 表外部化——那是后续独立 change `model-routes-externalize`。
- 不把 `max_tokens` 并入 `params`（仍是一等字段）。
- 不引入新依赖、不引入 settings.yaml。
- 不改 client 无状态语义（仍每次新建）、不改 MR1 的覆盖入口/字段级 merge/清空 fallback 既有行为。
- 不把采样参数写入 trace schema（`log_run` 不变）。

## Decisions

### D1：`RouteConfig` 新增 `params: dict[str, Any]`（per task_type 默认采样参数）
```python
@dataclass(frozen=True)
class RouteConfig:
    base_url: str
    model: str
    api_key_env: str
    max_tokens: int
    fallbacks: tuple[str, ...] = ()
    params: dict[str, Any] = field(default_factory=dict)
```
`params` 默认空 dict ⇒ 既有 `ROUTES` entry 不填即与现状逐字节一致。可按需为某 task_type 填默认采样参数（如 `memory_extraction` 设 `{"temperature": 0.0}`）。
**为何**：把「这个 task_type 用什么采样参数」收口在路由配置里，与 `max_tokens` 同源；frozen + default_factory 符合 router「不可变 config」既有风格。
**Alternatives**：①每个采样参数加一个一等字段（`temperature` / `top_p` / ...）——被否，见 D5；②不放 RouteConfig 而在 agent_loop 硬编码——被否，无法按 task_type 区分、违背 config 驱动。

### D2：`RouteOverride` 新增 `params: dict[str, Any]`，`_apply_override` 对 params 深合并
MR1 的 `RouteOverride` 增加 `params: dict[str, Any] = field(default_factory=dict)`。`_apply_override(cfg, override)` 计算 effective params 为 **base 与 override 的深合并**：以 `cfg.params` 为底，用 `override.params` 的键逐个替换/新增，未被 override 覆盖的 base 键沿用：
```python
effective_params = {**cfg.params, **override.params}
```
**为何**：满足「task_type 设一组默认采样参数，单次调用只想改其中一个键」的核心诉求——调用方只填要改的键，其余沿用 task_type 默认。语义可单测、可预测，与 MR1 字段级 merge 的「非 None 替换、未提供沿用」精神一致（params 维度用键级合并落实）。
**Alternatives**：整体替换（override.params 非空则忽略 cfg.params）——被否，会强迫调用方重复填全部采样参数，失去「只改一个键」的便利。

### D3：`max_tokens` 保持一等字段，`params` 只放其余采样参数
`max_tokens` 不并入 `params`，`create()` 调用形如：
```python
create(model=model, messages=messages, tools=schemas, max_tokens=cfg.max_tokens, **cfg.params)
```
**为何**：`max_tokens` 是既有一等字段，所有 `ROUTES` entry 都已填且语义稳定；并入 dict 会使既有 entry 与调用点全部改动、徒增回归面。保持分离 ⇒ 本 change 仅在 `create()` 末尾追加 `**cfg.params`，对既有路径零行为变化（`params` 为空时展开为空）。
**约束**：`params` 内**不得**再出现 `max_tokens` 键，否则会与显式 `max_tokens=` 形参冲突（`create()` 收到重复 kw 抛 `TypeError`）。这一点在 spec 场景固化、单测守卫。
**Alternatives**：把 `max_tokens` 也并入 params 做统一字典——被否，改动面大、与既有一等字段语义割裂。

### D4：优先级 = 调用覆盖 params > task_type params > provider 默认
解析链：取 base `RouteConfig`（含 task_type 默认 `params`）→ 经 `_apply_override` 与 `override.params` 深合并得 effective `params` → `**cfg.params` 透传 `create()`；某采样参数若三处都未出现，则**不传该 kw**，由 provider 取其默认。
**为何**：与 MR1 的覆盖优先级模型一致（调用级覆盖 task_type 级）；「不传即 provider 默认」保证既有空 `params` 路径行为不变，且不需要 router 知道每个 provider 的默认值。
**Alternatives**：router 内置各采样参数默认值——被否，provider 间默认不一（且推理模型根本不接受 temperature），router 不应假设。

### D5：用通用 `dict[str, Any]` 而非枚举式一等字段
采样参数容器用通用 dict，而非为 `temperature` / `top_p` / `frequency_penalty` 等各加一等字段。
**为何**：
- **推理模型差异**：o1 / thinking 类模型会**拒绝** `temperature`（传了报错），但有自己的参数（如 `reasoning_effort`）；枚举字段无法表达「这个模型不接受 temperature」，dict 可只填该模型支持的键。
- **provider 参数不一**：Anthropic 与 OpenAI 的采样参数名/取值并不完全一致，透传 dict 不需要 router 维护一张「字段 → provider」映射表。
- **lean 直调哲学**：项目禁止 AI 框架、直调 SDK；`**cfg.params` 直接展开成 `create()` 的 kwargs，正是「不加抽象层、透传底层 SDK 能力」的体现。
- **前向兼容**：SDK 新增采样参数时无需改 `RouteConfig` 结构，填进 dict 即用。
**Alternatives**：为每个采样参数加一等字段（`temperature: float | None = None` 等）——**被否**：①每加一个新参数都要改 `RouteConfig` / `RouteOverride` / merge 逻辑三处；②无法承载 provider 专有/推理模型专有参数；③需要 router 内置默认值或 None 过滤，复杂度高于直接透传；④与「直调 SDK、不加抽象」哲学相悖。

## Risks / Trade-offs

- [`params` 内误填 `max_tokens` 导致 `create()` 收到重复 kw 抛 `TypeError`] → D3 明确禁止、spec 场景固化、加单测守卫（`params` 含 `max_tokens` 时行为约定为不合法配置，测试断言其不出现于内置 `ROUTES`）。
- [深合并语义被误解为整体替换] → D2 固定 `{**cfg.params, **override.params}` 语义，spec 两个场景（部分键覆盖 / 新增键）固化，单测覆盖。
- [通用 dict 失去类型检查，错填参数名直到运行时才暴露] → 接受此取舍：换取推理模型/跨 provider/前向兼容能力（D5）；错填会在真实调用时由 SDK/provider 报错，单元测试 mock `create` 仅验证透传不验证 provider 接受度。
- [两个 create 调用点（sync 流式 / 非流式）需同步追加 `**cfg.params`] → 二者均在 `_*_with_fallback` 内单点修改，merge 逻辑全在共用的 `_apply_override`，无漂移；单测覆盖两条路径。
- [既有 `ROUTES` entry 未填 params 是否回归] → 默认空 dict，`**{}` 展开为空，`create()` 调用参数与现状完全一致；加回归守卫断言空 params 路径透传集合不变。

## Open Questions

- 是否为内置 `memory_extraction` route 预填 `{"temperature": 0.0}`——倾向预填以体现能力价值，但需确认 Anthropic endpoint 接受该 kw；实现时先以空 params 落地（保证零回归），预填值作为独立后续调整，不阻塞本 change。
