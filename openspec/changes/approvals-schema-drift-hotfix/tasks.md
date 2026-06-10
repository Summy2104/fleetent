# approvals-schema-drift-hotfix — Tasks

> 每个实现 task 严格 TDD：先写测试见红（`uv run pytest <file>::<test> -x -q`）→ 写实现见绿 → 可选 refactor 保持绿。
> 测试属 integration 层（真实 SQLite schema lifecycle），用 `tmp_path` 隔离，不触碰 `data/`。

## 1. 自愈补列 + 回填（核心修复）

- [ ] 1.1 写失败测试（integration）：`tmp_path` 下建旧形态 `approvals` 表（仅 `approver_user_id`，插入含历史审批人的行）→ 调 `ensure_schema(db_path)` → 断言 `approver_actor` 列存在、历史行回填取 `approver_user_id` 值、随后 `update_approval(..., approver_actor=...)` 成功——当前实现下此测试必须红（`no such column`）
- [ ] 1.2 实现：`ensure_schema` 建表后经 db.py 边界执行 `PRAGMA table_info(approvals)` 探测；缺 `approver_actor` 则 `ALTER TABLE ... ADD COLUMN`，并仅在该分支内回填 `UPDATE ... SET approver_actor = approver_user_id WHERE approver_actor IS NULL`；跑绿 1.1

## 2. 形态矩阵与幂等

- [ ] 2.1 写失败/确认测试（integration）：新形态库（当前 DDL 新建，无 `approver_user_id`）调 `ensure_schema` → 无 ALTER、无回填、结构数据不变（防止无条件回填引用不存在的列）
- [ ] 2.2 写失败/确认测试（integration）：双列形态库（两列都有、`approver_actor` 部分为 NULL）调 `ensure_schema` → 不回填，NULL 保持 NULL
- [ ] 2.3 写失败/确认测试（integration）：同一库连续两次 `ensure_schema` → 第二次不报错、结构数据不变（幂等）
- [ ] 2.4 实现/修正直至 2.1–2.3 全绿（若 1.2 实现已覆盖则确认绿即可，红→绿纪律以新增断言为准）

## 3. 并发防御

- [ ] 3.1 写失败测试（integration）：模拟补列竞态——预先在探测后、ALTER 前由「另一进程」补上列（测试内直接先 ALTER 再调含 ALTER 的路径，或 monkeypatch 探测结果为缺列）→ `ensure_schema` 捕获 `duplicate column` 的 `OperationalError` 视为已自愈，不抛出；其它 `OperationalError` 照常抛出
- [ ] 3.2 实现：仅吞 message 含 `duplicate column` 的 `OperationalError`（吞前 log），其余 re-raise；跑绿 3.1

## 4. 收尾

- [ ] 4.1 确认不 import platform、无新增裸 `sqlite3.connect`、SQL 用 named parameters（DDL/PRAGMA 除外）、不吞非预期异常
- [ ] 4.2 `make test-pr` 全绿 + `uv run pytest tests/integration -q`（不带 `-x`）对照 main 基线无新增失败
- [ ] 4.3 `openspec validate approvals-schema-drift-hotfix --strict` 通过
