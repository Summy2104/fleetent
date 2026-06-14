# Integration 测试漂移修复（2026-06-10）

> 背景：本地全量 `pytest tests/integration` 出现 **91 failed + 103 errors + 1 个永久挂起**。
> 由于 PR / main 的 CI 门禁只跑 unit（integration 是手动 custom pipeline），近期多个重构
> 「生产代码已改、集成测试未跟」一路绿灯入主干。本次以**最新功能代码为准**修复全部测试，
> 修复后基线：**integration 1637 passed / 0 failed**，**unit 2564 passed / 0 failed**（连续两轮）。

## 修复原则

1. **生产代码是真相源**：测试对齐最新行为/接口；仅当测试暴露真实生产缺陷时才改生产代码（本次 1 处，见 §C8）。
2. 不扩散修复范围：每类一个 commit，互不混杂。
3. 顺手修根因型测试基建（迁移模板、环境脆弱），消除整类问题而非逐个打补丁。

## 分类与决策

### C1 · 管理表入 Alembic，测试未跑迁移（~80 例）
- **现象**：`sqlite3.OperationalError: no such table: users / im_connectors / api_keys / legacy IM allowlist table`。
- **根因**：mgmt-tables-into-alembic / tenancy（迁移 067–070）后 `user_store._init_db()` 等变为 `pass`，管理表 **仅由 Alembic 建**；约 19 个测试文件的 fixture 仍只 `monkeypatch DB_PATH`、不跑迁移。
- **决策**：所有重定向 `DB_PATH` 的 fixture 在重定向后 `apply_migrations(db)`（必要处同步 `DATABASE_URL`）。

### C2 · session 重构删除 `session.index.DB_PATH`（80 例）
- **现象**：`AttributeError: session.index has no attribute 'DB_PATH'`（test_session_mgr 64 + test_session_index 16 全文件 ERROR）。
- **根因**：session-reliability 重构后 index 经 `DATABASE_URL` 解析 + `ensure_schema` 自建（agent-side 表）；fixture 还在 monkeypatch 已删除的常量。
- **决策**：fixture 改 `DATABASE_URL` + `ensure_schema(_db())`（与 agent boot 同路径）；删除冗余 `_init_db()` 调用。

### C3 · AgentFile 移除顶层 `bindings`/`access`（约 15 例，跨 8 文件）
- **现象**：`ValidationError: Extra inputs are not permitted (bindings / access)`；resolve 语义断言失败。
- **根因**：bindings 全量移除；`resolve_agent_for_request` 变为 **default-only**（部署态 `agents/default/agent.yaml` 为强制 default，多 agent 目录扫描不发布 default）；`access` 下沉为 `connectors.<platform>.access`。
- **决策**：
  - 路由/normalizer/integration 管线测试改用 **home 单 agent 部署态**（FLEETENT_HOME + `agents/default/agent.yaml`，`scan()` 无参），IM 准入写在 `connectors.slack.access.allow_users`。
  - 三个旧 channel/user 绑定优先级测试重写为新语义（多 agent 扫描 → None；单 agent → 任意 channel/user 都解析到 default）。
  - materialize 导出测试删除 `exported.bindings.*` 断言（生产已不导出）；config_overrides 测试改用现存字段（`knowledge.retrieval_policy.top_k`）。

### C4 · install 脚本拆分（14 例）
- **现象**：`Unknown option: --skip-db/--skip-config`、.bashrc 持久化 / docker 探测 / PATH 提示断言失配。
- **根因**：install-script-split 后 `install.sh` 是**开发者薄编排器**（editable 安装 + 委派 `install-agent.sh` / `install-platform.sh` + 自带 Alembic init）；旧单体行为随拆分移走。
- **决策**：重写 `test_install_script.py` 为新契约（新 flags、双委派、`--agent-only/--platform-only/--agent-id/--dir`、fake-uv 观测 alembic 目标库、幂等重跑）。

### C5 · slack 会话 id / create_app / 审批命令签名（6 例）
- **根因**：slack-context-and-session 把 `_derive_session_id` 改为 keyword-only（`channel_type/channel_id/user_id/thread_root`）且 id 形如 `slack:dm:U:TS` / `slack:thread:C:TS`；slack-assistant 使 create_app 注册 `app_mention`+`message` 双 handler 与 AsyncAssistant；审批 resolve 新增 `always=`（approve-always 最小化）。
- **决策**：测试对齐新签名/格式/注册集合；resolve 断言补 `always=False`。

### C6 · drop 迁移“downgrade -1 还原表”假设失效（4 例）
- **根因**：测试假设 head 即各 drop 迁移；tenancy 链推进 head 后 `-1` 撤销的是别的迁移。
- **决策**：还原断言改为**显式降到各 drop 之下**（quota→064、invites→065、askit→063、monitoring→062）；通用 roundtrip(-1) 保留。

### C7 · 路径派生测试对环境脆弱（6 例：4 unit + 2 integration）
- **根因**：模块路径常量在 **import 时**按环境冻结；测试 `delenv(FLEETENT_HOME)` 后与 call-time 解析比较——开发机 shell 若导出 `FLEETENT_HOME` 必挂（CI 未导出所以绿）。
- **决策**：改为**子进程受控环境**校验派生关系（剥离 FLEETENT_HOME 的子解释器内 `常量 == paths.X()`），环境无关且不 reload 污染本进程模块（agent_config 的 pydantic 类被广泛持有，reload 危险）。

### C8 · 审批/agent_app/杂项（~10 例）
- `agent_app` /ws 测试：旧 user_store api-key 鉴权 → 改 **FLEETENT_TUI_TOKEN**（tui-agent-auth）。过程暴露**真实生产 bug**：`agent_app.py` WS 拒绝路径调用 `_logger.warning`，structured_logging Logger 只有 `warn` → 路径必崩。**已修生产代码 1 行**（warning→warn，原 mypy 即报错）。
- 审批端点 happy-path：R1 **default-closed**（无可达 approver 即时拒绝）→ 测试需提供 routing + mock outbound 才有真正 pending；并在后台任务写入前隔离 `approval_store.DB_PATH`（import-time 冻结自环境家目录，曾打到真实家目录旧 schema 表）。
- standalone approval `'timeout'≠'approved'`：测试 patch 的是 `im_gateway.outbound` **re-export shim**，而 permission_gate import 自顶层 `fleetent.outbound` → patch 永不生效（CLAUDE.md 已记载的 shim-patch 陷阱）。改 patch 真模块。
- deployment_docs 完整性护栏：canonical `agents/default/agent.yaml.example` 缺 `action_gate_medium_mode / action_gate_high_mode / approval` → **补示例文档**（含注释样例）。

### 根因型基建修复（消类）
- **迁移模板**：`tests/integration/_migration_template._template_db()` 懒构建时若进程已 monkeypatch `DATABASE_URL`，alembic env.py 会迁移到那个库、模板 `head.db` 永不生成 → 后续所有 copy 失败（曾造成整批假 ERROR 与跨文件污染）。修复：构建期剥离 `DATABASE_URL`。
- **挂起测试**：`test_agent_scoped_isolation_e2e` 用 respx 模拟旧手写 JSON-RPC；MCP client 已重写为**官方 SDK**（streamable-HTTP 握手 + 重连循环）→ 永挂。重写为 **SDK 接缝 mock**（transport 捕获每连接 Authorization、session 回显凭证），凭证隔离断言原样保留。
- **隔离区解除**：`test_loop_permission_gate` 两个 flaky（旧 approvals 共享态）在 R1 后连续两轮全量 unit 全绿 → 移除 Makefile `PR_DESELECT` 隔离。

## 修复后基线

| 套件 | 结果 |
|---|---|
| `pytest tests/integration`（全量） | **1637 passed / 0 failed / 0 error**，无挂起 |
| `pytest tests/unit`（全量，无隔离区） | **2564 passed / 0 failed**（连续两轮） |

## 遗留建议（未在本 PR 实施）

- **把 integration 纳入 PR 门禁**（`bitbucket-pipelines.yml` 的 `pull-requests` 仅跑 unit；integration 是手动 custom pipeline）——否则同类漂移会再次累积。属 CI 策略变更，留给 owner 决策。
