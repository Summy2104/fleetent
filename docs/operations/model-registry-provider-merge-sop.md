# 同 vendor 多 provider 手动合并 SOP

> 适用场景：`model-registry-split` 迁移后，历史 `model_providers` 按 1:1 规则拆成 `providers` + `models`。若同一 vendor 出现多个 provider 行，需要运营人工收敛到共享凭证边界。

## 1. 何时需要合并

- 迁移后发现多个 `providers.vendor` 相同，且它们本应共享同一套凭证。
- 例外：同 vendor 但凭证、网络出口、租费归属或合规边界不同，不应合并。

## 2. 合并前检查

- 列出目标 vendor 下的全部 provider 与挂载模型：`GET /admin/providers` + `GET /admin/models`。
- 确认保留哪个 provider 作为最终凭证边界：
  - `api_key` / `api_key_env` 是正确的共享值。
  - `base_url` 仅作 UI 预填；不影响运行时寻址，不能作为是否保留的唯一依据。
- 通过 `GET /admin/providers/{id}/references` 记录当前被哪些 agent 间接使用，防止误判影响范围。

## 3. 合并步骤

1. 选定一个保留 provider，记为 `<target_provider_id>`。
2. 把同 vendor 下要收拢的模型逐个改到 `<target_provider_id>`：
   - 调 `PUT /admin/models/{model_id}`，只更新 `provider_id`。
3. 每迁一个模型后执行一次 `POST /admin/models/{model_id}/connectivity-test`，确认连接目标与共享 key 仍可用。
4. 当待删除 provider 的 `GET /admin/providers/{id}/references` 返回空 `models` 后，再删除该 provider。

## 4. 验收

- `GET /admin/providers` 中该 vendor 只剩预期的 provider。
- `GET /admin/models` 中相关模型都指向 `<target_provider_id>`。
- 受影响 agent 重新 materialize 后，`.env` 中引用的仍是保留 provider 的 `api_key_env`。
- 删除旧 provider 时若仍返回 409，说明仍有模型未迁走；先处理模型，不要强删。

## 5. 风险提示

- 不要为了“同 vendor”而合并本应隔离的不同凭证。
- per-agent key override 绑定的是 `provider.api_key_env`。若保留 provider 的 `api_key_env` 改名，相关 agent override 也要同步迁移。
- provider-health-probe 不在本 SOP 范围内；这里只处理平台 authoring 表，不改 agent 运行时熔断状态。
