# HANDOFF — file-exchange 系列（①②③④）交接

> 生成于 2026-06-13。基线：`main` = `4ffa31c`，当前分支 `feat/unified-file-exchange`（= main，空 diff）。
> 全程决策记录见 `docs/file-exchange-series-apply-decisions.md`（最详细，先读它）。

---

## 1. 总览

| Change | PR | 合并 | archive | 状态 |
|---|---|---|---|---|
| ① trace-tool-spans | #14 `2394cf3` | ✅ | ✅ | **完成** |
| ② conversation-address-unification | #15 `330b2e4` | ✅ | ✅ | **完成** |
| ③ unified-file-exchange | #16 `4ffa31c` | ✅ | ❌ | **部分（9/34）** |
| ④ delivery-receipts-postcondition | — | ❌ | ❌ | **未启动（0/10）** |

依赖链：① → ② → ③ → ④。④ 硬依赖 ③ 的 §6/§7 共享投递内核。

合入门禁（③ 合并前全过）：`make test-pr` 2937 passed；`mypy src` 89==main 89（零新增）；`tests/integration` 1965 passed / 0 fail。

---

## 2. ③ 已完成（已在 main）

**已勾选 9 任务**：§1 全部（1.1–1.6）、§2.1、§5 全部（5.1–5.2）。§2.2 **部分**（任务未勾）。

合入的代码全是**惰性附加脚手架**，现网行为字节不变（`artifact_exchange` 未被生产 import、约定注入未接 stdio 启动、无工具用 callable risk）。

**新增/改动文件：**
- `src/fleetent/artifact_exchange.py`（新）：`artifacts` 台账 store（`set_state_db`/`register`/`get`/`list_by_session`/`_find_by_path`，仿 schedule_store 注入）；`effective_root(server, agent_home)`（file_root > 显式 XDG > 约定 `<agent_home>/exchange/<id>/data`）；`register_server_root`；`resolve(path, session_id, *, approved=False)`（`/exchange` 命名空间 + 归属校验）；`ExchangeResolutionError`。
- `src/fleetent/runtime/agent_state_migrations.py`：迁移 **v32** 新增 `artifacts` 表 `{artifact_id PK, server_id, rel_path, session_id, user_id, filename, mime, size, created_at}`。
- `src/fleetent/integrations/mcp/client.py`：`McpServerConfig` 加 `file_root`/`file_isolation` 字段；`_subprocess_env(server, agent_home=None)` + `_convention_env` + `_convention_cwd`（约定注入纯函数，合并序 白名单<约定<显式 env，`file_isolation:off` 跳过，agent_home=None 走旧行为）。**注意：约定注入还没接到 `_transport_cm` 的 stdio 启动**（§2.2 残留）。
- `src/fleetent/tools/registry.py`：`RiskFn` 类型；`evaluate_risk_level(name, args, tool_context)`（callable 求值，异常 fail-closed medium）；`is_dynamic_risk(name)`；`get_risk_level` 对 callable 返回保守 "medium"。
- `src/fleetent/runtime/loop.py`：gate 处 `risk = get_risk_level(name)`，仅当 `is_dynamic_risk(name)` 才用 `evaluate_risk_level(name, args, tool_context)` 覆盖（静态风险行为字节不变）；`_plan_run_slots` 加可选 `tool_context` 形参并在调用点透传。

**新增测试（全绿）：**
- `tests/integration/test_artifacts_migration.py`、`tests/integration/test_artifact_exchange_store.py`
- `tests/unit/test_artifact_exchange_namespace.py`、`tests/unit/test_mcp_exchange_injection.py`、`tests/unit/test_registry_callable_risk.py`

---

## 3. ③ 未完成（25 任务，定义见 `openspec/changes/unified-file-exchange/tasks.md`）

| 任务 | 内容 | 卡点/依赖 |
|---|---|---|
| 2.2 残留 | stdio 启动接 cwd | 需「agent_home 在 transport 层怎么拿」 |
| 2.3 / 2.4 | 咽喉层把结果本地路径改写成 `/exchange` 并登记归因 | 需 scope key 穿线（见 §6 技术结论） |
| 2.5 / 2.6 | 调用窗口 diff 兜底登记 + per-server `asyncio.Lock` | 复杂度最高；是否必须取决于 discovery 决策 |
| 3.1 / 3.2 | fence 双根：file 工具接 `artifact_exchange.resolve` | 依赖 server-root 登记到位 |
| 4.1–4.8 | 硬链接归属视图 + Docker ro 挂载 `/exchange` + `BackendCapabilities.exchange_mount` + staging 降级 | **4.5 / 4.8 需 Docker** |
| 6.1–6.4 | send_file 接 `/exchange` + 升级审批（替换现 fail-closed 拒绝） | callable risk 机制已就绪 |
| 7.1 / 7.2 | send_im_message 加 `files` + 与 send_file 共享投递内核 | ④ 依赖此内核 |
| 8.1–8.4 | 收尾：全量 gate / 文档（AGENTS.md、agent.yaml.example）/ 真机重放 | 8.4 需 live |

## 4. ④ 未启动（10 任务，`openspec/changes/delivery-receipts-postcondition/tasks.md`）

1.1/1.2 `DeliveryReceipt` + `send_to`/`send_file_to` 返回回执 → 2.1/2.2 run 级台账 + `delivery` trace 事件 → 3.1–3.4 **事实尾注**（回复末尾如实附发了什么/失败什么，模型删不掉）→ 4.1/4.2 收尾 + 真机重放 AAA-8050。

---

## 5. 需讨论 / 待拍板（无 artifact，仅在对话 + 决策文档备注）

1. **根架构方向已选**：MCP 文件世界**并入 workspace 已有 scope 模型**——工件归属 = 该次 run 的 workspace scope key（scope=SESSION→session_id；scope=AGENT→agent_name），与 `/workspace` 挂载同源同 key。多人部署下 `integrations/sandbox/manager.py::resolve_workspace_scope` 已强制 `agent`→`session`（防跨用户泄漏），白捡隔离护栏。**不另起隔离轴。**
2. **两个待确认**：
   - 产文件的是不是 **stdio 本地 `google-workspace-mcp`**？（若是云端 HTTP，本套「本地文件交换区」机制完全不适用——文件不在本地，需走 future 的「远端字节拉回」另一条路）
   - **discovery 两层**（确定性咽喉改写为主 + 调用窗口 diff 兜底）定不定？建议：为正确性 diff 应做（结构成独立可测层），返不返路径只决定 diff 是主力还是安全网。
3. ✅ **已解决（2026-06-13）**：架构审计确认 agent 内文件/sandbox/exchange 只有一条隔离轴 = workspace scope key（platform 的 tenant_id 不入 agent；user_id 仅服务 memory/审批，非文件 key）。design.md/specs/tasks 已全量更新到「继承 workspace scope」：新增 **D0**（归属轴=scope_key、单一 key 派生权威、审计≠访问）；D3/D4/D5/D6 + 6 个 spec + tasks 同步；新增 **§0 归属轴重构任务**（`workspace_scope_key` 权威、迁移 v33 加 `scope_key` 列、重做已合入休眠代码的 `resolve`/`list_by_session`/`_find_by_path` 至 scope_key 轴并修「按路径取最新→误拒」缺陷）。`openspec validate --strict` 通过。**续做第一步 = §0**（§1.5/1.6 休眠产物被 §0 取代）。

---

## 6. 关键技术结论（续做必读，详见决策文档 ③ 节）

- **MCP 调用咽喉 `integrations/mcp/client.py::_call_via_session(server_id, tool_name, args, scope)` 只有 agent 级 `scope`，不带 IM session_id。** 这是 design 强调的「server agent 级长驻 vs workspace per-session」生命周期错配。
- 但 **`tools/registry.py::dispatch` 那层手里有 `tool_context`（含 session_id）**；agent 级 MCP 路径是 `dispatch → mcp_client.call_tool(..., scope=mcp_scope) → _call_via_session`（**绕开只收 `**kwargs` 的注册 wrapper**）。归属穿线从 dispatch 往下多传一道 scope key 即可，比想象干净。
- **共享子问题：agent_home 在 MCP 注册/transport 层怎么拿**。解了它一次性打通：§2.2 cwd、`register_server_root(effective_root(...))`、§2.3 改写时「路径是否落在有效根内」的判断。现 `_register_server` 手里是 `scope`（int），需确认 scope→agent_id→`paths.agent_home_dir` 这条映射能否干净拿到。
- fence：`tools/file_sandbox_io.py::resolve_host_path` 单根；`artifact_exchange.resolve` 已为 `/exchange` 第二根写好，§3 把它接进 read/write/edit/search。
- 沙箱：`integrations/sandbox/backend.py::BackendCapabilities`（加 `exchange_mount`）；`backends/docker.py::_workspace_flags`（仿它加第二卷 ro 挂载）；`manager.py::workspace_host_path`/`WorkspaceScope`。
- send 工具：`tools/builtin_tools.py` 的 `send_file`（~733，现 fail-closed）/`send_im_message`（~687，risk medium）。`send_file` 工具走 `tool_context.session_context`（platform/sender_id/chat_type）+ `outbound_connectors` 投递。

---

## 7. 建议续做顺序

1. 拍板 §5 的两个确认（stdio? discovery?）。
2. ✅ 已完成：design.md/specs/tasks 更新到「继承 workspace scope」根架构（见 §5.3）。
3. **先做 tasks §0**（归属轴重构：`workspace_scope_key` 权威 + 迁移 v33 + 重做休眠 `artifact_exchange`）——这是后续一切的地基。
4. 摸 agent_home 在 MCP 注册层的解析（解锁 2.2/2.3/3）。
5. 按依赖序实现：§0 → §2.2残留 → §2.3/2.4 →（§2.5/2.6 视决策）→ §3 → §4（§4.5/4.8 待 Docker）→ §6 → §7 → §8。
5. ③ 全勾后 `opsx:archive` + `opsx:sync` + PR 合并；再起 ④。

## 8. 流程/门禁速记（AGENTS.md）

- 每任务严格 TDD：`uv run pytest <file>::<test> -x -q` 先红后绿。
- change/PR 收尾：`make test-pr` 全绿 + `uv run pytest tests/integration -q` 对照 main 无新增失败 + `uv run mypy src` 无新增（基线 89）。
- commit 规范：`type(scope): 描述`（feat/fix/refactor/test/docs/chore）。
- 真机/Docker 依赖项（§4.5、§4.8、各 change 的真机 smoke）：本环境无法验证，待有 Docker/live IM/model 的环境跑。
