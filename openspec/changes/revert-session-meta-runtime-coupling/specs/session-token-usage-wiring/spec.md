## REMOVED Requirements

### Requirement: run() 通过 usage_out 出参透出 token usage

**Reason**: `usage_out` 出参当初只为给 normalizer→`save(token_usage=)` 喂 token。token 既走 observability trace，save 不再需要 token，则该出参无消费方。

**Migration**: 移除 `run()`/`_run_inner` 的 `usage_out` 参数及填充逻辑。

### Requirement: normalizer 将 token usage 传给 save

**Reason**: agent 侧不再向 platform 写 token；该 wiring 回退。

**Migration**: normalizer 不再建 usage_out、不再向 `save` 传 `token_usage`。
