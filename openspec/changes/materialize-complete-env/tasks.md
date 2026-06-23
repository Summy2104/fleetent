## 1. 统一 env-name 收集器（D2）

- [x] 1.1 写测试（unit）：共享收集器对一个引用了 model `api_key_env` + `embedding.api_key_env` + `rerank.api_key_env` + `telegram.bot_token_env` + mcp `*_env` 的 AgentFile，返回**全部**这些名（flatten 口径）；先见红
- [x] 1.2 实现：把 `materialize._env_var_names` 的 flatten 逻辑提为共享 public 函数（runtime 侧可 import 的位置），令 1.1 见绿
- [x] 1.3 `runtime/agent_init.referenced_env_names` 改为复用共享收集器（或薄 re-export）；跑既有 agent_init 测试确认仍绿（必要时更新断言为全集）

## 2. node 物化写完整 .env（D1/D3，env-only）

- [x] 2.1 写测试（unit/node）：`_write_home` / `ensure_env_scaffold` 对有 secrets 的 agent，写出 `0600` 的 `.env`，含全部引用名；本轮下发了值的名为真实值、未下发的为空占位；含保留的 `FLEETENT_TUI_TOKEN`；先见红
- [x] 2.2 写测试（unit/node）：已存在含 `FLEETENT_TUI_TOKEN` 的 `.env`，重写后 token 不变（幂等保留）；先见红
- [x] 2.3 实现：`ensure_env_scaffold` 演进为"写完整 `.env`（名+值+`0600`）"，值由调用方（node reconcile）传入 desired-state.`secrets`；令 2.1–2.2 见绿
- [x] 2.4 写测试（unit/node）：`backend.spawn` **不再**经 `Popen(env=secrets)` 注入 secret（secret 仅在 `.env`）；先见红
- [x] 2.5 实现：node reconcile 把收到的 secrets 传给 `.env` 写入而非 spawn 注入；移除 `backend.spawn` 的 secret 注入路径；令 2.4 见绿
- [x] 2.6 确认顺序：写 `agent.yaml` → 写完整 `.env`(`0600`) → `backend.spawn`

## 3. node-secret-injection 契约更新（缓存 / platform-down 韧性）

- [x] 3.1 写测试（unit/node）：desired-state 磁盘缓存仍 strip secret（缓存内容无 secret 值）；先见红→实现/确认见绿
- [x] 3.2 写测试（integration）：platform 不可达时，已物化（`.env` 含真值）的 agent 可从盘上 `.env` 重启，不因缺 secret 推迟；先见红→实现见绿

## 4. 生命周期擦除（D4）

- [x] 4.1 写测试（unit/node）：agent 从期望集移除（unpin/disable）被停后，其 home `.env` 被擦除；擦除失败舱壁化（只 log、不影响其它 agent）；先见红
- [x] 4.2 实现：node reconcile 在停掉不再期望 agent 后擦除其 `.env`，舱壁化；令 4.1 见绿

## 5. 暴露面加固（D6）

- [ ] 5.1 写测试（unit/integration）：diagnostics 导出排除 `<home>/agents/*/.env`，manifest 仅记 redacted 引用摘要；先见红
- [ ] 5.2 实现：把 agent home `.env` 纳入 diagnostics 导出/备份排除清单（复用既有 secret/SQLite 排除机制）；令 5.1 见绿
- [ ] 5.3 写测试（unit）：redaction 兜底对 `.env` 形态 `KEY=<token-like>` 脱敏；先见红→实现见绿

## 6. 平台侧对齐与收尾

- [ ] 6.1 确认平台 `materialize._seed_env` 与 node 走同一收集器口径，两条路径产物一致（写/更新对照测试）
- [ ] 6.2 文档：在部署文档标注 prod 前提（`.env` `0600` + home `0700` + platform↔node TLS）；按 AGENTS.md 非代码产物须人工确认后再 commit
- [ ] 6.3 跑 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` 确认无新增跨包 internal import 违规
- [ ] 6.4 change 收尾：`make test-pr` + `make test-unit-ci`（覆盖率门禁）全绿，对照 main 无新增失败；相关 node/runtime/diagnostics integration 测试无新增失败
