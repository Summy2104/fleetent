> chore 减法(移除非功能 quota 半成品)。纪律:删除后既有测试**保持全绿**;删表迁移**可逆往返**;删代码前**二次 grep 确认零调用**。

## 1. 删除 quotas / quota_usage 表(迁移)

- [ ] 1.1 写迁移测试(`tests/integration/`):空库 `alembic upgrade head` 后断言 schema **不含** `quotas`/`quota_usage`(注:它们本由运行时 _init_db 建,fresh alembic 库可能本就没有——断言"不存在"即可)。
- [ ] 1.2 新增 Alembic 迁移:`upgrade()` `DROP TABLE IF EXISTS quotas; DROP TABLE IF EXISTS quota_usage`;`downgrade()` 按 `quota._init_db` 原 DDL 重建二表。
- [ ] 1.3 可逆性:空库 `upgrade head` → `downgrade -1`(重建)→ `upgrade head`(再 drop)往返干净通过。

## 2. 删除 quota 代码

- [ ] 2.1 二次核实:`grep -rn "governance.quota\|check_quota\|record_usage\|set_quota\|_emit_over_quota" src tests`,确认无非测试调用点。
- [ ] 2.2 删除 `src/fleetent/governance/quota.py`。
- [ ] 2.3 删除 `src/fleetent/server.py::_emit_over_quota_event`(及其任何引用)。

## 3. 清理测试

- [ ] 3.1 删除/改写引用 quota 的测试(grep 出的测试文件),保持全绿。

## 4. 收尾验证

- [ ] 4.1 `make test-pr` 全绿。
- [ ] 4.2 `uv run pytest tests/integration -q` 对照 main 基线无新增失败;server 启动 + `/chat` 既有测试无回归。
- [ ] 4.3 `openspec validate descope-quota` 通过。
- [ ] 4.4 复核:未碰 permission_gate / blocklist / audit / user_store / 请求路径。
