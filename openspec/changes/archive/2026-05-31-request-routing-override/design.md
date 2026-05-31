## Context

`model_router.py` 是 agent_loop 与底层 provider 之间唯一的中间层：`get_async_client_and_config(task_type)`（行 51）从 `ROUTES` 取 `RouteConfig`（frozen dataclass，含 `base_url` / `model` / `api_key_env` / `max_tokens` / `fallbacks`），再 `os.environ` 取 key 实例化 `AsyncOpenAI`，返回 `(client, cfg)`。`agent_loop.py` 的 `run()`（行 153）与 `run_stream()`（行 314）均硬编码 `get_async_client_and_config("default")`，并用 `models_to_try = [cfg.model, *cfg.fallbacks]`（行 169 / 330）驱动 `_call_with_fallback` / `_stream_with_fallback`。

本 change 是 docs/capabilities/model-router.md「规划中（v1.0）」的 `请求级路由覆盖`，也是后续「成本感知路由」「子 agent 降级」的地基。首要目标是把覆盖接口设计成对调用方零侵入（不传即现状），且不破坏 router「无状态、config 驱动、OpenAI-compatible SDK」三条原则。

约束（CLAUDE.md）：禁止 AI 框架；禁止 ORM；禁止全局可变状态；router 用 OpenAI-compatible SDK 且 config 驱动；mypy strict；行长 100；TDD Hard Gate；测试 mock LLM，不发真实请求。

## Goals / Non-Goals

**Goals:**
- 在 `get_async_client_and_config` / `get_client_and_config` 引入可选 `override` 参数，单次调用按字段覆盖 task_type 路由结果。
- 用 `RouteOverride`（frozen dataclass，字段全可选）承载覆盖意图，接口不堆散参数。
- 覆盖语义清晰：非 None 字段覆盖、None 字段沿用 task_type 结果；强制指定模型时默认不走原 fallback 链。
- `run()` / `run_stream()` 暴露 `force_model: str | None`，为 None 时与现状逐字节一致。
- 覆盖后最终模型写入 trace（复用 `log_run` 既有 `model_used`）。

**Non-Goals:**
- 不实现成本感知路由（按预算自动降级）——后续独立 change。
- 不实现健康探针缓存 / fallback 跳过——见并行 change `provider-health-probe-cache`。
- 不改 `ROUTES` 表结构，不新增 task_type，不引入 settings.yaml。
- 不改 client 无状态语义（仍每次新建）、不改 fallback 遍历算法本身。

## Decisions

### D1：用 `RouteOverride` 数据类承载覆盖，而非散参数
新增 frozen dataclass：
```python
@dataclass(frozen=True)
class RouteOverride:
    model: str | None = None
    base_url: str | None = None
    max_tokens: int | None = None
    api_key_env: str | None = None
    fallbacks: tuple[str, ...] | None = None
```
`get_async_client_and_config` / `get_client_and_config` 签名末尾增加 `override: RouteOverride | None = None`。
**为何**：覆盖维度可能增长（temperature、extra_params 等），用单一 dataclass 承载比在两个函数上各加 4+ 散参数可维护；frozen + 全可选符合 router「不可变 config」既有风格（`RouteConfig` 即 frozen）。
**Alternatives**：①直接加 `model: str | None = None` 等多个散 kw——被否，接口随维度膨胀、两个函数需重复维护；②直接传整个 `RouteConfig` 覆盖——被否，强制调用方填全部字段，失去「只覆盖模型」的便利与「沿用其余」的语义。

### D2：字段级 merge 语义，None 即「沿用 task_type 结果」
解析时先按 task_type 取 base `RouteConfig`，再对 override 每个非 None 字段做替换，得到 effective config，再实例化 client。
**为何**：满足「同一 task_type、仅换模型」的核心诉求——调用方只填 `model`，`base_url` / `api_key_env` 等自动沿用同一 provider；语义可单测、可预测。
**Alternatives**：整体替换（override 在则忽略 task_type）——被否，会强迫调用方重复填 base_url/key，违背便利目标。

### D3：强制指定模型时默认清空 fallbacks
当 `override.model` 非 None 且 `override.fallbacks` 为 None 时，effective config 的 `fallbacks` 取空 tuple；调用方若确需 override 后仍有 fallback，显式传 `override.fallbacks`。
**为何**：请求级覆盖的语义是「这次就用这个模型」，若仍回落到原 task_type 的 fallback 链会偏离调用方意图（如想用 haiku 却回落到 sonnet）。`agent_loop` 侧 `models_to_try` 因此在 override 生效时仅含单一模型。
**Alternatives**：覆盖 model 但保留原 fallbacks——被否，语义自相矛盾，且可能把临时降级又抬回主模型。

### D4：`agent_loop` 暴露 `force_model`，为 None 时零变更
`run()` / `run_stream()` 增加 `force_model: str | None = None`：
- None：`override = None`，`get_async_client_and_config("default")`，`models_to_try = [cfg.model, *cfg.fallbacks]`，与现状一致。
- 非 None：`override = RouteOverride(model=force_model)`，`get_async_client_and_config("default", override=override)`，`models_to_try = [cfg.model]`（cfg 已是覆盖后结果，fallbacks 已空）。
**为何**：给调用方一个最小、自解释的旋钮；不传不改任何现有行为，回归风险最低。
**Alternatives**：在 `run()` 暴露完整 `RouteOverride`——被否，当前唯一明确诉求是换模型；保留以后按需扩展，不提前过度设计。

### D5：trace 复用既有 `model_used`，不新增字段
`log_run` 已有 `model_used`；覆盖后传入 effective model 即真实记录本次模型，无需 schema 变更。
**为何**：改动最小，向后兼容；事后即可从 trace 区分「task_type 默认模型 vs 本次强制模型」。

## Risks / Trade-offs

- [override 与 fallback 语义混淆，调用方误以为覆盖后仍有 fallback] → D3 明确「覆盖 model 默认清空 fallbacks」，spec 场景固化，单测覆盖两种情形。
- [覆盖了 model 但 base_url/key 不匹配导致鉴权失败] → D2 字段级 merge 默认沿用同一 provider 的 base_url/api_key_env，只有调用方显式覆盖 base_url 才会换 provider，符合预期。
- [两个 router 函数（sync/async）需同步维护 merge 逻辑] → 把 merge 抽成单一私有纯函数 `_apply_override(cfg, override) -> RouteConfig`，两函数共用，避免漂移。
- [`get_client_and_config` 缺 key 时抛 RuntimeError、async 版本用空串] → 现状两者行为本就不同，本 change 不改该差异，仅在 override 后保持各自原有 key 处理路径。

## Open Questions

- 是否需要在 `RouteOverride` 暴露 `temperature` / `extra_params`——当前 `RouteConfig` 无这些字段（仅 docs 接口草案有），本次不引入，待 router 自身补齐这些字段后再扩展 override。
