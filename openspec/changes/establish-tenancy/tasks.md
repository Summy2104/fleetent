> 严格 TDD(每个实现 task 先写最窄测试见红→实现见绿)。迁移须**幂等 + 可逆往返** + **在有数据的库上安全**(回填只补空)。先做迁移前核查(D 风险)。

## 1. 迁移前核查

- [ ] 1.1 核查现有 `agents`/`knowledge_*`/`traces`/`policies` 的 `tenant_id` 取值:确认都为 `"default"`;若有他值,迁移需为这些值建对应 tenant 行(否则升 FK 会失败)。记录结论。

## 2. tenants / teams 实体 + 迁移

- [ ] 2.1 写失败测试(`tests/integration/`):空库 `alembic upgrade head` 后 schema 含 `tenants`、`teams`(uuid 字符串 id,`teams.tenant_id` FK→tenants),且存在 id=`"default"` 的主体。先见红。
- [ ] 2.2 新增 Alembic 迁移:建 `tenants(id,name,status,created_at,approver_user_id?)`、`teams(id,tenant_id FK,name,approver_user_id?,created_at)`;建 default 主体。见绿。
- [ ] 2.3 可逆性:空库 `upgrade head`→`downgrade -1`→`upgrade head` 往返通过。

## 3. users 纳入 alembic + tenant_id

- [ ] 3.1 写失败测试:`users` 由 alembic 建出且含 `tenant_id`(NOT NULL、FK→tenants);`user_store` 不再 `_init_db` 建 `users`;`User`/`_FULL_COLS` 含 `tenant_id`;在已有用户库上跑迁移后所有 user `tenant_id="default"`。先见红。
- [ ] 3.2 实现:迁移把 `users` 纳入 alembic、加 `tenant_id` 列、回填 `"default"`、置 NOT NULL + FK;`user_store` 去掉 `users` 的 `_init_db` 建表、`User` dataclass 与 `_FULL_COLS` 加 `tenant_id`、CRUD 带上它。见绿。
- [ ] 3.3 现有 `agents/KB/traces/policies.tenant_id` 与 `agents.team_id` 升 FK(值不变);测试断言现有值保留、FK 生效。

## 4. 两级 approver 字段

- [ ] 4.1 写失败测试:`tenants.approver_user_id` / `teams.approver_user_id`(可空、FK→users);设置/读取正确。先见红。
- [ ] 4.2 实现(迁移已加列;tenancy store 暴露设置/读取)。见绿。

## 5. 最小 provisioning(admin)

- [ ] 5.1 写失败测试:admin 入口 create tenant / create team / set user.tenant_id / set tenant|team approver;受 admin 鉴权;写审计;非 admin 拒。先见红。
- [ ] 5.2 实现 tenancy store + admin CLI/API(沿用现有 admin 鉴权 + audit_log)。见绿。

## 6. 收尾验证

- [ ] 6.1 `make test-pr` 全绿。
- [ ] 6.2 `uv run pytest tests/integration -q` 对照 main 基线无新增失败;在"已有数据"的库上跑迁移幂等、不破坏现有 users/agents。
- [ ] 6.3 `openspec validate establish-tenancy` 通过。
- [ ] 6.4 复核范围:未做物理分区 / 未重写各 store 的查询 tenant 过滤 / 未碰 principal / 未建 team_members;部署文档标注"部署须先 `alembic upgrade head`"与"物理隔离(#3)前勿灌真敏感 A/B 数据"。
