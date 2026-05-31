## Context

`agent_loop.py` 的 `_call_with_fallback`（行 74）/ `_stream_with_fallback`（行 102）接受 `models: list[str]`（来自 `[cfg.model, *cfg.fallbacks]`），按序 `for model in models` 尝试 `client.chat.completions.create(model=...)`，仅捕获 `RateLimitError`（429）与 `APIStatusError` 503 作为「可 fallback」信号，其余异常直接 re-raise；全部失败则 `raise last_exc`。当前**无任何失败记忆**：某 provider 持续故障时，每次请求仍先打它、等超时再切走，放大延迟。

本 change 是 docs/capabilities/model-router.md「规划中（v1.0）」的 `健康探针缓存`，与 `request-routing-override` 互不依赖，但**依赖 AR5（error-classification）并排其后**：失败判定复用 AR5 的 `classify()`（见 D6），避免在 fallback 循环里与 AR5 重复异常判定。首要目标是给 fallback 遍历加一层「跳过已知不健康 provider」的缓存，同时严守项目「无全局可变状态」「无新依赖」原则。

约束（CLAUDE.md）：禁止 AI 框架；禁止 ORM；禁止全局可变状态（缓存必须可 monkeypatch 注入）；router/agent_loop 用 OpenAI-compatible SDK；新模块结构 import → 常量 → 数据类 → 函数；mypy strict；行长 100；TDD Hard Gate；测试 mock LLM，不发真实请求，不 sleep。

## Goals / Non-Goals

**Goals:**
- 缓存每个 provider（按 model 标识）的连续失败计数与「不可用截止时间」。
- 连续失败达阈值 → 标记不可用并进入冷却；冷却期内 fallback 遍历跳过该 provider。
- 冷却期满 → 半开重试（重新进入候选）；成功恢复、失败重入冷却。
- 任一成功调用立即清零失败计数、清除不可用标记。
- 阈值与冷却时间经 `Settings` env 字段配置 + 构造参数覆盖。
- 缓存为可注入实例，无全局可变状态，测试可隔离。

**Non-Goals:**
- 不实现主动健康探针（后台定时 ping provider）——本次是「被动」探针：靠真实请求的成功/失败更新状态。
- 不实现成本感知路由 / 请求级覆盖（见并行 change `request-routing-override`）。
- 不改非 429/503 异常的直接 re-raise 语义。
- 不持久化健康状态（进程内内存缓存即可，进程重启清空）。
- 不改 `ROUTES` / `RouteConfig` 结构、不引入 settings.yaml。

## Decisions

### D1：被动探针——靠真实调用结果更新状态，不引后台任务
`_call_with_fallback` / `_stream_with_fallback` 每个 model：成功 → `record_success(model)`；429/503/连接错误 → `record_failure(model)`。无独立线程/定时器主动探测。
**为何**：零新依赖、零新基础设施，符合「本次只接零基础设施依赖」边界；fallback 遍历本就在打真实请求，复用其结果即天然探针。
**Alternatives**：后台主动健康探针（定时 ping）——被否，引入调度/线程、增加复杂度与 provider 额外负载，超出本次范围（可作后续 change）。

### D2：`ProviderHealthCache` 可注入实例 + `ProviderState` 数据类
新增 `src/fleetent/provider_health.py`：
- `ProviderState` 数据类：`consecutive_failures: int`、`unavailable_until: float`（monotonic 时间戳，0 表示可用）。
- `ProviderHealthCache`：内部 `dict[str, ProviderState]`；方法 `is_available(model) -> bool`、`record_failure(model)`、`record_success(model)`；构造参数 `failure_threshold` / `cooldown_seconds` / `now: Callable[[], float]`（默认 `time.monotonic`，测试可注入假时钟）。
- 模块级单例 `_cache: ProviderHealthCache`，配可替换 getter（同 `session_mgr` 风格），测试 monkeypatch 注入隔离。
**为何**：避免全局可变状态裸露（CLAUDE.md 硬规则）；`now` 可注入使时间相关逻辑无需 `sleep` 即可单测；实例封装比模块级散字典清晰。
**Alternatives**：①模块级裸 dict——被否，全局可变状态、难隔离；②每次 fallback 新建缓存——被否，失败记忆无法跨请求保留，失去缓存意义。

### D3：阈值经 Settings 配置 + 构造参数覆盖（对齐 context_mgr / termination 模式）
- `config.py` 的 `Settings` 增加 `provider_failure_threshold: int = 3`、`provider_cooldown_seconds: int = 60`（env 可配，与 `agent_max_turns` 等同类）。
- `provider_health.py` 提供 `_default_config()`：惰性 `from fleetent.config import Settings`（同 `context_mgr` / `termination`），返回阈值 dict。
- `ProviderHealthCache` 构造参数 > Settings（env）> pydantic 字段默认值。测试传构造参数或传 config 注入，不实例化真 `Settings`（避免 `anthropic_api_key` 必填）。
**为何**：项目所有运行旋钮（context 阈值、permission 超时、agent_max_*）一律走 Settings env 字段；再引 YAML 既违「无新依赖」也与现有代码割裂；Settings 默认值即单一事实来源。
**Alternatives**：①模块级 `DEFAULT_*` 常量——被否，与 Settings 默认值重复、不可 env 配置；②settings.yaml——被否，文件不存在、机制不符。

### D4：fallback 遍历跳过不健康 provider，且全部不可用时不空遍历
遍历前用 `is_available(model)` 过滤候选；若过滤后**列表为空**（全部冷却中），为不静默失败，仍对原始候选做半开尝试（取冷却中候选按截止时间排序后逐个试），或直接抛上一轮记录的代表性异常——实现首步据现有测试期望择一并固化到 spec。核心不变量：**绝不返回「无候选可试」的静默空结果**。
**为何**：保证「所有 provider 耗尽时抛异常由上层处理」的既有契约（docs 场景 3）不被健康跳过破坏。
**Alternatives**：过滤后为空即直接 raise——简单但可能在全部短暂冷却时过早放弃；半开兜底更稳健。具体取舍在实现首步确认（见 Open Questions）。

### D5：半开重试与恢复语义
`is_available(model)`：`unavailable_until == 0` 或 `now() >= unavailable_until` 返回 True（后者即半开放行一次）。半开放行后：调用成功 → `record_success` 清零并置 `unavailable_until=0`；失败 → `record_failure` 累计，达阈值重新置冷却。`record_failure` 达阈值时 `unavailable_until = now() + cooldown_seconds`。
**为何**：经典断路器「闭合/开启/半开」三态，行为可预测、可单测；冷却到点自动半开无需额外定时器。
**Alternatives**：固定次数后永久剔除——被否，provider 恢复后无法自愈，违背「暂时不可用」语义。

### D6：失败判定复用 AR5 的 classify()（依赖 error-classification，排其后）
本 change **依赖 AR5（error-classification）并排其后实施**。失败判定不再自定义异常类型，而是复用 AR5 的 `classify(exc)`：`record_failure` 当且仅当 `classify(exc).should_switch_model` 为真（即 `rate_limit`：429/503）。其余分类（`auth_failed` / `unknown` 等 `should_switch_model` 为假）→ 不计失败，按现状 re-raise。
**为何**：AR5 与 MR3 都改同一处 fallback 循环的 except 分支，统一用分类层判定可消除重复的异常类型判断，两 change 干净叠加；且「哪些算 provider 失败」与「哪些该切模型」语义天然一致。
**连接/超时错误**：AR5 为「保持可观察行为不变」未把连接/超时归为可切换（现状连接错误直接 re-raise、不 fallback）。故本次 MR3 的断路仅覆盖 `should_switch_model` 为真的 429/503；**连接/超时的断路留作后续**——待 AR5 增设可切换的连接错误分类后，MR3 经 `classify` 自动覆盖，无需再改 MR3。
**Alternatives**：MR3 自定义 429/503/连接错误判定——被否（用户选 A），与 AR5 重复且需各自维护、易漂移。

## Risks / Trade-offs

- [缓存把短暂抖动的 provider 错误关停太久] → 冷却时间可经 Settings env 调小；半开机制使冷却到点即自动重试；阈值默认 3 次连续失败才触发，避免单次抖动误判。
- [全局可变状态违反 CLAUDE.md 硬规则] → 封装为可注入 `ProviderHealthCache` 实例 + 可替换模块单例，测试 monkeypatch 注入，时间用可注入 `now`。
- [`_call_with_fallback` 与 `_stream_with_fallback` 两份遍历逻辑漂移] → 健康判定/记录全部走同一 `ProviderHealthCache` API，两处仅调用同一方法；用例覆盖两条路径。
- [全部 provider 同时冷却导致请求直接失败] → D4 保留半开兜底/抛代表性异常，绝不静默空结果，维持「耗尽即抛异常」既有契约。
- [并发请求竞争同一缓存导致计数错乱] → 计数为简单整数自增、状态最终一致即可（容忍轻微竞争，断路器语义对偶发偏差不敏感）；如需严格一致后续可加 `asyncio.Lock`，本次不引入以免过度设计。

## Open Questions

- D4 全部冷却时的兜底策略（半开逐个试 vs 直接抛）——以 `tests/test_agent_loop.py` 既有「provider 耗尽抛异常」期望为准，实现首步确认后固化到 spec。
- D6 连接/超时异常的精确类型（`APIConnectionError` / `APITimeoutError`）——以 openai SDK 实际为准，实现首步核实。
- `provider_failure_threshold` / `provider_cooldown_seconds` 默认值最终取值——本次给保守默认（3 / 60s），后续随运行治理统一收口。
