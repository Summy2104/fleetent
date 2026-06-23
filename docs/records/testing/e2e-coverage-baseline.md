# E2E 覆盖基线（as-built）

> **现状权威参考**——只描述"当前 `tests/e2e/` 端到端覆盖了哪些场景"。这是**活文档**：任何 change 新增/删除/改动 e2e 场景，MUST 同步本表。
> **真相源是测试代码**：场景描述以 `tests/e2e/*.py` 的实际断言为准；每条能力的需求级定义见 `openspec/specs/e2e-*/spec.md`。
> **运行**：整套 `make test-e2e`（= `uv run pytest tests/e2e`）；单文件 `uv run pytest tests/e2e/<file>.py -q`。
> **门禁定位**：多进程 e2e 在**独立 slow lane**，**不进** per-merge `make test-pr`，也不在 CI per-merge pipeline（沿用"e2e 默认不进 PR 门禁"）。

## Harness 说明

所有 managed e2e 都跑**真实多进程拓扑**，不是单进程 + mock：

- **`conftest.py::managed_stack`**（核心 fixture，自地基落地后冻结不动）：起 platform 进程 + node 进程 + 每 agent 子进程，经真实 forwarder/HTTP 通信；隔离临时 home + 迁移好的临时管理库（不碰 `data/`）、动态端口、注入 dev master key、走 node-provision 落 service key；teardown 反序干净停。
- **`_llm_stub.py`**：本地 OpenAI 兼容 SSE LLM stub，确定性回复，agent 经 model `base_url` 指向它——断言固定、不调真 LLM。
- **每波独占 helper / stub**（不碰核心 fixture，保证并行无冲突）：`_tenant_helpers.py` / `_kb_helpers.py` / `_cron_helpers.py` / `_im_helpers.py`（含 `managed_agent_route_server`：起 `fleetent agent run --no-im --port` 子进程拿可达 `/im/route`）/ `_oidc_stub.py` + `_identity_helpers.py` / `_reflection_helpers.py`。

## 覆盖矩阵

状态：✅ 跑通 ｜ ⏭️ 条件性 skip（注明原因/补救）

### managed-stack-coverage — 多进程栈根能力
| 测试 | 场景 | 状态 |
|---|---|---|
| `test_llm_stub_streams_deterministic_reply` | LLM stub 确定性流式回复 | ✅ |
| `test_managed_stack_starts_platform_node_and_agent` | 三进程起栈互联（node 注册→spawn agent→健康） | ✅ |
| `test_managed_chat_ingress_streams_stub_reply` | **chat ingress 端到端流式**：admin 登录→`/admin/agents/{name}/chat`→platform→node→agent→stub→流式回 operator | ✅ |
| `test_node_lifecycle_fetches_desired_state_and_reports_running_agent` | node 拉 desired-state→spawn agent 子进程→`/health` 健康上报 | ✅ |

### multi-tenant-isolation — 多租户数据隔离（P1）
| 测试 | 场景 | 状态 |
|---|---|---|
| `test_two_tenant_agents_ready_and_data_roots_independent` | 两 tenant 各起一 agent、数据根目录各自独立 | ✅ |
| `test_cross_tenant_query_no_data_bleed` | **跨租户查询零串数据**（tenant-a 写的，tenant-b 查不到） | ✅ |
| `test_file_level_physical_isolation` | 文件级物理隔离（`<data_dir>/<tenant>/...` 互不覆盖） | ✅ |

### kb-chain — 知识库全链
| 测试 | 场景 | 状态 |
|---|---|---|
| `test_kb_ingest_and_search_direct` | KB ingest→检索直查命中（确定性 embedding，零外部） | ✅ |
| `test_kb_content_injected_into_agent_prompt` | **检索结果注入 agent prompt**（经 stub 验 KB 内容进了上下文） | ✅ |
| `test_kb_retrieval_audit_trace_recorded` | 检索 audit trace 被记录 | ✅ |

### sandbox-cron — 沙箱执行 + 定时触发
| 测试 | 场景 | 状态 |
|---|---|---|
| `test_run_code_executes_in_sandbox_and_folds_output_to_reply` | run_code 在 agent loop 沙箱执行并回折回复 | ⏭️ **无 Docker daemon 时优雅 skip**（设计预期；有 Docker 即跑） |
| `test_cron_task_fires_and_writes_run_state` | cron 任务定时 fire→写 run-state（调度器在 agent 进程内） | ✅ |

### im-inbound-approval — IM 入站 + 审批 + directed-reach
| 测试 | 场景 | 状态 |
|---|---|---|
| `test_im_route_replies_with_stub_text` | `/im/route` 入站→loop→同步回复 | ✅ |
| `test_im_route_high_risk_tool_queues_approval_dm` | **高危工具→审批 DM 入队** `im_outbound_queue` | ✅ |
| `test_im_route_approve_command_resumes_pending_run` | **`approve <id>` 经 /im/route→恢复挂起的 run** | ✅ |
| `test_directed_queue_row_advances_after_user_binding_lookup` | directed-reach notify_user fan-out 投递原语（directed 行→node 反查用户绑定地址后推进） | ✅ |

### identity-flow — OIDC / email 并号 / 跨渠道 link
| 测试 | 场景 | 状态 |
|---|---|---|
| `test_oidc_stub_endpoints_and_rp_validation` | mock OIDC issuer（RS256 签名/jwks）端点 + RP 校验 | ✅ |
| `test_oidc_login_provisions_user_and_creates_session` | **OIDC 登录建 User + 建 session** | ✅ |
| `test_oidc_callback_reuses_existing_email_user_without_duplicate_create` | **email 并号**（同 email 再登录复用同一 User，不重复建） | ✅ |
| `test_link_confirm_binds_identity_rejects_reuse_and_unlinks` | **/link 跨渠道绑定** + 拒绝重复绑定 + unlink 解绑 | ✅ |

### reflection-lifecycle — 反思提案生命周期
| 测试 | 场景 | 状态 |
|---|---|---|
| `test_reflection_enabled_managed_agent_emits_scheduler_report` | reflection-enabled agent 的 scheduler 定时出报告 | ✅ |
| `test_memory_mark_stale_proposal_can_be_approved_via_im_route` | **memory mark_stale 提案经 /im/route 审批→apply** | ⏭️ skip（managed agent gateway 不可发现）；**修复 `e2e-reflection-route-server` 已 propose、待 apply** |
| `test_reflection_scheduler_generates_pending_skill_proposal_from_repeated_task_pattern` | scheduler 从重复任务模式生成 pending skill 提案 | ✅ |

## 刻意不在 managed e2e 覆盖（由别处保障）

- **fan-out / 出站队列真投递腿**（消息真从 node drain 投到 transport）：integration `tests/integration/test_node_im_outbound_queue.py` 覆盖。managed e2e 无真 connector，只断言入队 + 反查地址。
- **真 Slack/Telegram transport 适配层**：`tests/e2e/test_slack_autonomous_smoke.py` + slack-e2e-autonomous 套件覆盖（需 `SLACK_E2E_TOKEN` 等，默认 skip）。
- **microsandbox microVM 后端**：`test_microsandbox_backend_smoke.py`（需 `FLEETENT_RUN_E2E=1` + 预装 runtime，默认 skip）。

## 已知缺口 / TODO

1. **reflection 的 approve→apply 半程** —— 当前 skip（gateway 不可发现）；fix change `e2e-reflection-route-server` 已 propose（复用 `_im_helpers.managed_agent_route_server`），apply 后本格转 ✅、reflection-lifecycle 名副其实。
2. **沙箱执行** —— 仅在有 Docker 的环境跑；CI/本机无 Docker 时 skip。
3. **MCP + Vault**（MCP 工具调用 + per-principal 凭据解析）—— 未做，按需再上（需新建 `_mcp_stub`）。

## 预存烟测（非本批，背景参考）

`test_platform_boot_smoke.py`（platform uvicorn /health）、`test_agent_serve_smoke.py`（`agent run` /health）—— 单进程启动烟测，先于多进程 harness 存在。

## 相关

- 能力需求：`openspec/specs/e2e-*/spec.md`（managed-stack-coverage / multi-tenant-isolation / kb-chain / sandbox-cron / im-inbound-approval / identity-flow / reflection-lifecycle）
- 整合背景：本批多进程 e2e 补完工作流（地基 harness + 7 波覆盖）从 2026-06-22 起、2026-06-23 主体落地。
