## 1. A3 · 删平台 resolve 端点（TDD）

- [ ] 1.1 落地前核查：`grep -rn "approvals/.*resolve" src/ frontend/ tests/` + openapi/前端客户端，确认 `server.py` 的 resolve 端点除单测外无消费者（有则先停下评估）。
- [ ] 1.2 改测试（先红）：把 `tests/unit/test_platform_admin_api_unit.py` 中针对 `server.resolve_approval` 的用例改为断言该端点**不存在**（或删除该用例 + 加一条"platform 不暴露 resolve"的断言）。先跑见红。
- [ ] 1.3 实现（绿）：删 `server.py` 的 `@app.post("/approvals/{id}/resolve")` 函数 + `ApprovalRequest` 模型（确认无其它引用）+ `resolve_approval_request` import（若仅此处用）。保留 `list_approvals` 等只读投影。重跑见绿。
- [ ] 1.4 回归：`agent_app` 的 resolve 端点单测仍绿（agent 侧 resolve 通道未受影响）。

## 2. A4a · routing key helper（TDD）

- [ ] 2.1 写测试（先红）：针对 `_proposal_routing_key(domain, action)`——skill→`reflection_skill_proposal`；
  memory+`suggest_shared_memory_or_kb`→`reflection_shared_memory_proposal`；memory+其它（mark_stale/rewrite/…）→`reflection_user_memory_proposal`。先跑见红。
- [ ] 2.2 实现（绿）：在 `reflection/reflection.py` 加纯函数 `_proposal_routing_key`。见绿。

## 3. A4a · 两处生成点接入 helper（TDD）

- [ ] 3.1 写测试（先红）：断言**同一提案在 notify 与 create 两处用同一 routing key**——
  patch/spy `resolve_approvers`/`approval_request_store.create_request`，对一条 user-memory 提案断言两处都收到
  `reflection_user_memory_proposal`，对一条 shared 提案都收到 `reflection_shared_memory_proposal`，skill 提案 `reflection_skill_proposal`。先跑见红。
- [ ] 3.2 实现（绿）：`_create_proposal_approval_request` 与 `_notify_pending_proposal`
  （及 `_schedule_pending_proposal_notification`）各增 `action` 入参，内部用 `_proposal_routing_key` 替换原
  `f"reflection_{domain}_proposal"`。所有调用点（706 user-memory / 970 shared / 992 skill）传对 action（skill 可传 None）。重跑见绿。

## 4. spec 文档对齐（archive 时同步）

- [ ] 4.1 `opsx:archive` 同步 `approval-request-lifecycle` spec：MODIFIED "统一审批路由按主体类型分派 resolve"
  （加 resolve 入口仅 agent 侧 / platform 只读、reflection 提案按域+目标细分 routing key + 两个新场景）。delta 已在 change specs/ 下。

## 5. 收尾门禁

- [ ] 5.1 `make test-pr` 通过（对照 main 基线无新增失败）。
- [ ] 5.2 `make test-unit-ci` 通过（CI 覆盖率关 coverage --fail-under=76）。
- [ ] 5.3 跑相关单测（reflection 路由 + platform_admin_api + approval_router/gate 相关），无新增失败。
- [ ] 5.4 `uv run python scripts/check_module_boundaries.py` 通过。
