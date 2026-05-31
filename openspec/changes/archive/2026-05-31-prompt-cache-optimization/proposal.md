## Why

agent 主循环每一轮都把 system prompt + tools schema + 完整历史重发给 LLM。其中**稳定前缀**（system + tools + 早期消息）是提示缓存（prompt caching）的理想对象：命中缓存时输入 token 成本大幅下降（自托管 vLLM 自动前缀缓存 / OpenAI 自动缓存可达数倍节省）、延迟降低。对多轮 agent 对话收益显著。

但现状有两个问题：

1. **提示组装把可变内容放在了前缀最前面，等于关闭了缓存**。`run_sync` / `run_stream` 现以 `full_system = f"{memory_ctx}\n\n{system_prompt}"` 再追加命中的 skill——**每请求都变的 `memory_ctx`、每输入都不同的 matched skill 被放在 system 消息最前**。前缀一变，自动前缀缓存每次失效，永远命中不了。
2. **没有任何缓存命中可观测**：无法回答"当前后端缓存命中率多少"。

此外，AR12（双阈值压缩）的设计理由写明"保护 prompt 缓存、减少缓存失效"——但缓存从未被真正利用（前缀不稳定）。本 change 把这盏灯打开。

## What Changes

- **稳定可缓存前缀**：重排提示组装，让**稳定的 `[base system + tools]` 位于最前**作为可缓存前缀；把**可变的 `[memory 注入、命中的 skill]` 移到其后**（独立后续消息 / 首个 user turn 内），使其变化不再使前缀缓存失效。按稳定度排序（base 最稳 → memory → skill → 对话）以最大化可缓存前缀长度。
- **缓存指标写入 trace**：从 API `usage` 提取缓存指标（如 Anthropic `cache_read_input_tokens` / `cache_creation_input_tokens`、OpenAI `prompt_tokens_details.cached_tokens`，按后端存在与否尽力提取），经 `log_run` 记入运行日志，建立命中率基线。
- **后端无关、不引入 `cache_control` / 不换 SDK**：依赖**自动前缀缓存**（vLLM APC / OpenAI 自动），不使用 provider 专有的缓存标记。生产 on-prem 后端为自托管 vLLM（自动前缀缓存），continue 走现有 OpenAI 兼容 SDK。
- **与 AR12 协调**：压缩时 MUST 保留可缓存头部（base system + tools + 稳定前缀），只压缩对话尾部，避免无谓改写前缀使缓存失效。

## Capabilities

### New Capabilities
- `prompt-cache-optimization`: 通过稳定可缓存前缀（base system + tools 置前、可变 memory/skill 后置）让自动前缀缓存能命中，并将缓存命中指标记入 trace；后端无关、不引入 `cache_control` 或新 SDK。

### Modified Capabilities
<!-- 无既有 spec 的需求级行为变更。发给 LLM 的"内容集合"不变，仅调整其在消息序列中的顺序以利缓存；功能行为（system/memory/skill 都生效）保持等价。 -->

## Impact

- **代码**：
  - 修改 `src/fleetent/agent_loop.py`：`run_sync` / `run_stream`（及 `run` 的消息组装）调整 system/memory/skill 的拼装顺序——base system 作为稳定前缀，memory_ctx 与 matched skill 后置；从 `usage` 提取缓存指标传入 `log_run`。
  - 修改 `src/fleetent/eval_logger.py`：`log_run` 增加缓存指标参数（如 `cache_tokens: dict | None = None`，默认 None 向后兼容，非 None 写入 entry）——加性字段，同 `stop_reason` 模式。
- **配置**：无新增 Settings 字段、无新依赖。
- **测试**：`tests/test_agent_loop.py` 补充：组装后 base system 在可变 memory/skill 之前（前缀稳定性断言）、功能等价（memory/skill 仍生效）；缓存指标从 mock `usage` 提取并传入 `log_run`。LLM 调用按规范 mock。
- **依赖**：**依赖 AR12（compression-dual-threshold）**——压缩需保留可缓存头部；本 change 排在 AR12 之后，二者一起使"压缩保护缓存"自洽。
- **不影响**：model fallback、终止框架、工具 dispatch、permission_gate；不改 `match`/`load`/记忆提取的功能行为（仅注入位置变化）。
