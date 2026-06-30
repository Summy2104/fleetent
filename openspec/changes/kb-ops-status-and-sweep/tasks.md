## 边界（先读）
只动 `serve.py`、`worker.py`、`operations.py`(读 helper)、`kb_ingest_jobs.py`(list helper)、`standalone_sweep.py`(若需）。
**严禁碰**(D2' 地盘）：`service_config.py`、`kb-service.yaml.example`、`config.py`/`agent_config.py`。

## 1. 状态读取 helper（TDD）

- [ ] 1.1 测试先行：列本租户 connector 状态(`operations`)、列近期 ingest job(`kb_ingest_jobs`,按 tenant/kb，含 status+结果)。现仅 get-by-id → 加 list/by-tenant。见红→实现见绿

## 2. kb-serve GET /status（TDD）

- [ ] 2.1 测试先行：合法 Bearer+principal `GET /status` → 返回 connector 状态 + 近期 job;跨租户(principal.tenant_id≠绑定)拒绝。见红
- [ ] 2.2 实现：`serve.py` 加 `GET /status` handler，复用 `_require_authorized_principal`,调 §1 helper

## 3. sweep 解耦到 kb-worker（TDD）

- [ ] 3.1 测试先行：kb-worker 的 run 循环按 `sync_interval_seconds` 到期对连接器入队(不依赖 kb-serve）;只起 worker 即有调度。见红
- [ ] 3.2 实现：`worker.py` 的 `run()`(:308 循环)按 interval 调 `standalone_sweep.sweep`;`serve.py` lifespan 删 `_sweep_loop`(:137-142)
- [ ] 3.3 确认 kb-serve 启动后不再起 sweep task(纯读）

## 4. 收尾门禁

- [ ] 4.1 `openspec validate kb-ops-status-and-sweep --strict`
- [ ] 4.2 `make test-pr` + `make test-integration-ci` 全绿
- [ ] 4.3 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py`（未碰 platform）
- [ ] 4.4 `git diff --name-only main` 自查：不出现 service_config.py / kb-service.yaml.example / config.py / agent_config.py（那是 D2'）
- [ ] 4.5 功能分支 `openspec archive kb-ops-status-and-sweep`（同步 kb-read-service + kb-standalone-ingest spec）
- [ ] 4.6 所有 checkbox 标 `[x]`
