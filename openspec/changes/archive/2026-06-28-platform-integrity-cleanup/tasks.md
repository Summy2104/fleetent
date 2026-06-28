# Tasks:平台数据完整性与门控收尾

> 三组(P1/P2/P3)**各自独立 commit**,不混。每个实现 task 前先写测试见红。最窄命令 `uv run pytest <file>::<test> -x -q`。

## 1. P1 — agent 引用/生命周期完整性卫生(纯代码,无迁移;独立 commit)

- [x] 1.1 写测试:agent 仅有非 user 绑定(MCP / KB / IM group / service grant / 或有 node placement)时,归档请求被 409 阻断且响应列出引用类型。先红。
- [x] 1.2 实现:`references()` 增查 `agent_im_groups`/`agent_mcp_servers`/`agent_kbs`/`agent_service_grants`/`agent_placements`,归档保护按全引用集合判定(保留硬阻断)。跑 1.1 见绿。
- [x] 1.3 写测试:对有 `node_agent_status` running 行的 agent 执行 `unpin_agent` 后该行被删;`deregister_node` 后该 node 的上报行被删。先红。
- [x] 1.4 实现:`unpin_agent` / `deregister_node` 同步 `DELETE FROM node_agent_status`(按 agent_id / node_id)。跑 1.3 见绿。
- [x] 1.5 删死函数 `get_agent_for_user()`(agent_store.py)及其测试引用;跑受影响 unit 层见绿。
- [x] 1.6 P1 收尾:受影响层(unit + 相关 integration)无新增失败 → 作为 P1 单独 commit。

## 2. P2 — 禁用外部服务即门控(纯代码,无迁移;独立 commit)

- [x] 2.1 写测试:`external_services.enabled=false` 的服务,即便已有 `authorized` 凭证,vault provider 解析也返回"未授权"等价结果(不注入 `Credential`、不抛异常);`enabled=true` 正常放行。先红。
- [x] 2.2 实现:在 `vault_provider` 解析链(OAuth + apikey 两路)读 `external_service_store.get_service(...).enabled`,false 时走 NeedsConsent 风格未授权返回。跑 2.1 见绿。
- [x] 2.3 P2 收尾:受影响层无新增失败 → 作为 P2 单独 commit。

## 3. P3 — 租户 FK 完整性(Alembic 迁移 106;独立 commit)

- [x] 3.1 写测试 + 实现**脏数据预扫**(迁移首步):孤儿 `api_keys`(user_id 无匹配 user)→ 迁移内 DELETE 并记日志;跨租户 `agents.team_id` 引用(team.tenant_id ≠ agent.tenant_id)→ **显式报错并列出违例行**,中止迁移。先写两类脏数据的检测测试见红。
- [x] 3.2 写测试:迁移到 head 后 —— `teams` 有 `UNIQUE(id, tenant_id)`;`agents` 复合 FK 拒绝跨租户 team 直写;`api_keys` 删除 user 级联清 key;且**干净库**迁移成功(沿用 migration 测试范式,含数据)。先红。
- [x] 3.3 实现 Alembic 迁移 106(接当前 head;apply 时先 `uv run alembic heads` 取真实 head,勿硬编码):预扫(3.1)→ `teams` 加 UNIQUE →`agents` batch 重建为复合 FK `(team_id,tenant_id)→teams(id,tenant_id)` ON DELETE RESTRICT → `api_keys` batch 重建加 FK CASCADE。downgrade 反向可逆。跑 3.1/3.2 见绿。
- [x] 3.4 确认 store 层 `create_agent`/`update_agent_tenancy` 的既有一致性校验保留(双层防护,不删)。
- [x] 3.5 P3 收尾:迁移相关 + 全量 integration 无新增失败 → 作为 P3 单独 commit。

## 4. 收尾验证(整个 change)

- [x] 4.1 `make test-pr` + `make test-unit-ci`(76% 覆盖率)+ `make test-integration-ci`(**全量**,本 change 含 DB 迁移=跨切面)+ `make test-frontend` 全绿,判据"对照 origin/main 基线无新增失败"。
- [x] 4.2 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` 通过。
- [x] 4.3 确认本 change **不改 agent 配置物化**(agent.yaml 内容不变)→ desired-state 哈希不变 → 不触发运行中 agent 批量 respawn(无需哈希稳定性专项,但确认 materialize 未被触碰)。
