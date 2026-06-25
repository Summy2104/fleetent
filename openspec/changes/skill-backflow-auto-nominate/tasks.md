## 1. 平台：drift 自动提名回流（去重、best-effort）

- [ ] 1.1 写测试（integration，新建 `tests/integration/test_backflow_auto_nominate.py`）：复用 `test_backflow_governance` 的 pool/agent/home 物化套路（pool git 提交某 skill、agent 绑定 + `materialize.write_home` + 进化 home 副本），`FLEETENT_SKILLS_DIR` 指向 pool；`POST /nodes/{id}/status` 上报该 skill `drift=true` → 断言 `agent_skills.drift=1` 且 `backflow_proposals` 新增 1 条 pending（agent_id/skill_name 正确、`proposed_bundle` 非空）。先见红
- [ ] 1.2 写测试（integration）：在 1.1 状态上**再次**上报同 skill `drift=true`（已有 pending）→ 断言 pending 仍为 1 条（去重，不重复生成）。先见红
- [ ] 1.3 写测试（integration）：上报 `drift=false` → 断言不生成提案；且既有 pending（若有）不被该上报关闭/改动。先见红
- [ ] 1.4 写测试（integration）：best-effort——`monkeypatch` `backflow_store.nominate_if_absent` 抛异常 → 断言 `POST /nodes/{id}/status` 仍 200、该函数**被调用过**（spy，提供红前提）、`agent_skills.drift` 仍正确落库。先见红
- [ ] 1.5 实现：`backflow_store.nominate_if_absent(*, agent_id, skill_name, pool_dir) -> int | None`（先 `list_proposals(status="pending")` 短路去重、否则 `nominate(...)`）；`node_desired_state_api._project_skill_status` 对 `skill.drift` 为真者调用之（`pool_dir=_skill_pool_dir()`），`try/except` 舱壁化（模块 logger 记 warning、不传播）；补模块 logger（若无）。令 1.1–1.4 见绿
- [ ] 1.6 单 task 收尾：跑 `tests/integration/test_backflow_auto_nominate.py` 与 `tests/integration/test_node_desired_state_api.py` 确认无新增失败

## 2. 平台：回流读端点 + 路由挂载

- [ ] 2.1 写测试（integration，扩 `tests/integration/test_backflow_governance.py` 或新建 `test_backflow_read_endpoints.py`，复用其 `app`/`admin_token`/`pool_dir`/`_nominate`）：`GET /admin/skills/backflow` 列出 pending（条目含 `id/status/agent_id/agent_name/skill_name/base_version/base_commit/conflict/created_at`，**不含** `proposed_bundle`）；无 token → 401；非 admin → 403。先见红
- [ ] 2.2 写测试（integration）：`GET /admin/skills/backflow/{id}/diff` 返回 `diff_vs_base`/`diff_vs_head`/`conflict`；不存在的 id → 404；需 admin（401/403）。先见红
- [ ] 2.3 实现：`backflow_api` 加 `GET ""`（list 薄包 `list_proposals(status=...)`，剔 `proposed_bundle`、补 best-effort `agent_name`）与 `GET "/{proposal_id}/diff"`（薄包 `get_proposal_diff(..., pool_dir=_pool_dir())`，`ValueError`→404），均 `_require_admin`。令 2.1–2.2 见绿
- [ ] 2.4 写测试（integration，扩 `tests/integration/test_server.py`）：真实 `fleetent.server:app` 上 backflow 路由可达——`/admin/skills/backflow`（list）、`/{id}/diff`、`/{id}/accept|reject|fork` 均在 `app.routes`；未鉴权访问 list 返回 401（而非 404，证明已挂载）。先见红
- [ ] 2.5 实现：`server.py` 加 `from fleetent.platform.skill_management import backflow_api` 与 `app.include_router(backflow_api.router)`。令 2.4 见绿
- [ ] 2.6 单 task 收尾：跑受影响 integration 文件确认无新增失败

## 3. 前端：回流审批 UI

- [ ] 3.1 写测试（前端，`frontend/src/features/skills/api.test.tsx`）：`useBackflowProposalsQuery`（GET `/admin/skills/backflow`）、`useBackflowDiffQuery`（GET `.../{id}/diff`）、`useBackflowAccept/Reject/ForkMutation`（POST 正确 URL + `Session` 头；冲突 accept 带 `X-Confirm: true`；fork 带 `{fork_name}` body）——经 MSW 断言请求方法/URL/头/body。先见红
- [ ] 3.2 实现：`frontend/src/features/skills/api.ts` 加 backflow types + query/diff/mutation hooks（沿用 `useAdminApi()` + React Query 既有范式）。令 3.1 见绿
- [ ] 3.3 写测试（前端，`frontend/src/features/skills/page.test.tsx`）：回流审批区列出 pending、点 "View backflow diff" 展示 diff、accept/reject/fork 三按钮触发对应请求；`conflict=1` 项 accept 需二次确认（`window.confirm` mock → true，请求带 `X-Confirm: true`），confirm 取消则不发请求。先见红
- [ ] 3.4 实现：`page.tsx` 加「Skill backflow」审批区（仿现有 reflection 只读区版式，带 accept/reject/fork 决策按钮 + 冲突二次确认 + fork 名输入）。令 3.3 见绿
- [ ] 3.5 单 task 收尾：跑 `frontend/` vitest 相关用例确认绿

## 4. 收尾与门禁

- [ ] 4.1 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` 通过（确认 `node_desired_state_api → skill_management.backflow_store` 合规、无 node→platform、无跨包 internal import 违规）
- [ ] 4.2 `make test-pr` 全绿
- [ ] 4.3 `uv run pytest tests/integration -q`（不带 `-x`）对照 main 基线无新增失败
- [ ] 4.4 前端 `npm --prefix frontend run test`（或仓内既定 vitest 命令）相关用例通过
- [ ] 4.5 风险验证（只读）：确认 `materialize` 旧 rematerialize/`_copy_skills` 路径不会重置 managed（有 placement）agent 的 drift——读代码核实其 drift 写作用域，记录结论于本 task；若发现确会打架，停下来与人对齐再决定是否扩范围
