## 1. requester 哨兵解析（agent_config）

- [x] 1.1 Write failing tests for `resolve_approvers` sentinel: `["requester"]` 返回 `("requester", "")`；与外呼地址混排共存；恶意格式（`requester:xxx`）不被误识别
- [x] 1.2 Implement sentinel parsing in `resolve_approvers` to pass tests

## 2. requester 路由（permission_gate）

- [x] 2.1 Write failing tests for requester routing: 哨兵路由时审批提示经 `reply_func` 发出（含 approve/reject 指引）且无外呼；混排时双通道都通知；纯哨兵且发起人 resolve 后正常放行（短超时 `PermissionGate(medium_timeout=0.1)`）
- [x] 2.2 Implement requester routing in `request_approval`/`_notify_approvers` to pass tests

## 3. 决策身份校验（permission_gate）

- [x] 3.1 Write failing tests for decision authorization: 非授权身份 resolve 返回 False 且 pending 保持；requester 本人可决策；被通知的外呼审批人可决策；未被通知的配置地址不可决策
- [x] 3.2 Implement authorized-actor set recording + `resolve()` enforcement to pass tests

## 4. 收尾

- [x] 4.1 新增/更新决策文档 `docs/approval-and-outbound-decisions.md`（分层判据、哨兵语义、身份校验补洞说明、迁移姿势）
- [x] 4.2 受影响层收尾：`uv run pytest tests/unit -q` 无新增失败；`make test-pr` 全绿；`uv run pytest tests/integration -q` 对照基线无新增失败
