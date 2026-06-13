# retire-legacy-api-key-and-agent-rename Tasks

> 每个实现 task 严格 TDD：先写测试见红，再实现见绿。测试任务在对应实现任务之前。

## 1. API key 回填迁移（Alembic）

- [x] 1.1 [测试] integration：升级路径——旧库带 `users.api_key` 明文值（含 NULL/空值行）升级到 head 后：`users` 无 `api_key` 列、每个明文 key 对应一行哈希 `api_keys`（scope `["*"]`、无过期、归属同 user）、**原明文 key 经 authenticate 仍认证成功**；重复运行幂等（先红）
- [x] 1.2 [实现] 提取/复用与 platform 侧完全同源的 key 哈希函数；新增 Alembic 迁移（同迁移内：回填 → drop 列）→ 1.1 转绿

## 2. 单轨化代码改造（user_store / identity / CLI）

- [x] 2.1 [测试] unit/integration：`create_user` 后 `api_keys` 有哈希行、`users` 行无 key 值、明文经返回值交付一次；admin CLI `create-user` 输出仍含一次性明文 key（先红）
- [x] 2.2 [测试] integration：resolver 未注入（standalone 形态）时 `authenticate` 经本地 `api_keys` 哈希比对成功/拒绝（valid / revoked / expired / blocked 四态）；`LocalBearerAdapter` 对有效 key 返回 Principal、无效返回 None（先红）
- [x] 2.3 [测试] unit：守护——`user_store.py` 与 `identity.py` 无按 `users.api_key` 列查找的代码路径（无 `_get_by_legacy_key` 等字面量）；`platform.user_management` 无 `migrate_api_keys`；两模块零 platform import（既有护栏维持）（先红）
- [x] 2.4 [实现] `user_store`：`create_user` 落新轨 + 返回形态调整（D3）、`authenticate` 本地 `api_keys` fallback 替换 legacy 路径、删 `_get_by_legacy_key` / `get_legacy_api_keys` / `_FULL_COLS` 的 `api_key`；`identity.LocalBearerAdapter` 换数据源 + docstring；删 `platform.user_management.migrate_api_keys`；`User` dataclass 去 `api_key` 字段，全仓调用方同步 → 2.1–2.3 转绿
- [x] 2.5 [核实] 全仓 grep `\.api_key`（属性/键名）与 `users.api_key` 清零（迁移历史与 openspec 归档除外）

## 3. agent rename 拆除

- [x] 3.1 [测试] unit：守护——`agent_store` / `agent_admin_store` / agent console API 无修改 `agents.name` 的函数或端点（先红：rename_agent 等存在）
- [x] 3.2 [实现] 删 `agent_store.rename_agent`、`agent_admin_store.rename`、console `rename_agent_def` 死桩及相关测试/引用 → 3.1 转绿；全仓 grep `rename_agent` 清零（归档除外）

## 4. 文档

- [x] 4.1 `docs/architecture/data-model.md` §3.2：`users` 描述去 legacy `api_key` 注记、改为"key 唯一真相源在 `api_keys`（哈希，明文不落库）"；`agents` 描述加 **name 为不可变标识**（admin_state / session_meta / 物理目录以其为键）
- [x] 4.2 复核 `docs/capabilities/platform.md` / `user-center` 相关描述与 `docs/deployment/`（install/pilot 手册中 create-user 流程输出）无旧轨表述，有则同步

## 5. 收尾

- [x] 5.1 `make test-pr` 全绿；`uv run pytest tests/integration -q`（不带 `-x`）对照 main 基线无新增失败
- [x] 5.2 `openspec validate retire-legacy-api-key-and-agent-rename` 通过；所有 checkbox 标记 `[x]`
