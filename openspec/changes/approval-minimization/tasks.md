## 1. 指纹纯函数 + allow-list 存储

- [x] 1.1 Write failing unit tests `tests/unit/test_approval_allowlist.py`：`fingerprint(scope, tool, args)` 对相同输入稳定、对 args 键序无关（`{"a":1,"b":2}` == `{"b":2,"a":1}`）、对值/工具/scope 敏感（任一不同→不同指纹）（tests/unit）
- [x] 1.2 Implement `governance/approval_allowlist_store.py` 的 `fingerprint`（canonical json + sha256）+ `ensure_schema`/`is_allowed`/`add_grant`/`list_grants` 骨架，pass unit tests
- [x] 1.3 Write failing integration tests `tests/integration/test_approval_allowlist_store.py`：真实 SQLite——add_grant 后 is_allowed 为真、未授予为假、list_grants 返回、重复 add 幂等（tests/integration，tmp_path DB）
- [x] 1.4 Implement store CRUD（named params、SQLiteDatabase、db_path 可注入），pass integration tests

## 2. request_approval 命中指纹自动放行

- [x] 2.1 Write failing unit tests：指纹在 allow-list 中→`request_approval` 返回 "approved" 且**不调用** `_notify_approvers`、写一条 auto_approved 审计；不在 allow-list→照常走 notify（mock store + mock notify）（tests/unit，permission_gate 短超时）
- [x] 2.2 Implement request_approval 前置查指纹（scope=requester_user_id）+ pending 指纹记账，pass unit tests

## 3. resolve allow-always 持久化

- [x] 3.1 Write failing unit tests：`resolve(id, "approved", approver, always=True)` 把 pending 指纹写入 allow-list（mock/真实 store）；`always=False`（默认）不写；`reject` + always 不写（tests/unit）
- [x] 3.2 Implement resolve 增 `always` 参数 + 授予分支，pass unit tests

## 4. IM `approve always` 解析

- [ ] 4.1 Write failing unit tests `tests/unit/test_normalizer_approve_always.py`：`approve always <id>` → resolve 以 always=True 调用；`approve <id>` → always=False；`reject <id>` 不变（mock _default_gate.resolve）（tests/unit）
- [ ] 4.2 Implement `normalizer._APPROVAL_RE` + route 分支传 always，pass unit tests

## 5. 收尾验证

- [ ] 5.1 解耦验证：新增模块零 platform import；模块依赖护栏 + schema drift guard 通过（新表 ensure_schema-only 不破坏 guard）；无 platform DB 环境下指纹自动放行可用
- [ ] 5.2 全量收尾：`make test-pr` 全绿（approval-routing/action-gate 回归不破）＋ ruff/mypy 改动文件 + integration 对照 main 基线无新增失败 + 本机 `uv run alembic heads` 单 head（推前 merge 最新 main）
