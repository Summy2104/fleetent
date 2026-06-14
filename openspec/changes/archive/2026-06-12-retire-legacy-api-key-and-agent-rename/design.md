# retire-legacy-api-key-and-agent-rename Design

## Context

核实的事实链：`create_user`（user_store.py:77）每个新用户写明文 key 进 `users.api_key`；`authenticate`（:104）resolver 优先、legacy 列 fallback；**standalone bearer 认证整体建在 legacy 列上**（`identity._legacy_key_lookup` → `_get_by_legacy_key`，`LocalBearerAdapter` docstring 明写 "using only the local users.api_key column"）；canonical `user-store` spec 现把 `api_keys` 定性为"platform 专属表、standalone 不查询"——这正是 LocalBearerAdapter 被锁在 legacy 列上的根因。rename 侧：`agent_store.rename_agent`（:451）可用、`agent_admin_store.rename` 有 re-key、console `rename_agent_def`（console_api.py:100）是 `return None` 死桩；`session_meta.agent_name` 无 re-key；**物理目录 `agents/<name>/data/` 以名字为键**。

## Goals / Non-Goals

**Goals:**
- API key 单轨：`api_keys` 哈希表为唯一真相源，明文不落库；managed / standalone 同一数据源
- standalone bearer 行为不变（有效 key → Principal），仅换底层数据源
- agent rename 半成品拆除，name 不可变写成 spec 约束

**Non-Goals:**
- 不做完整 rename 支持（B 案）：物理目录搬迁含停机/竞态问题，产品无此需求前不投入
- 不动 `api_keys` 表 schema 与平台侧 key 生命周期管理（吊销/过期/scope 逻辑原样）
- 不动密码登录 / session 认证路径（仅 bearer key 数据源）

## Decisions

**D1：standalone 解析改为本地直查 `api_keys` 哈希，spec 的"不查询该表"定性同步修正**
原 spec 把 `api_keys` 划为"platform 专属、standalone 不得查询"，是 #4 时期防反向依赖的过度防御——边界的本质约束是 **import 方向**（agent 不得 import platform），不是表的读访问：standalone 一直在读同库的 `users` 表，读 `api_keys` 与之同级。哈希比对函数放 `user_store` 本地（共享 store），`LocalBearerAdapter` 调它，护栏（零 platform import）不变。否决方案"standalone 改用 FLEETENT_TOKEN 静态令牌"：行为变化大、丢掉 per-user 身份。

**D2：回填走 Alembic 数据迁移（先回填后 drop，同一迁移内两步骤）**
存量明文 key 哈希后 INSERT 进 `api_keys`（scope `["*"]`、无过期、`INSERT OR IGNORE` 级幂等、跳过 NULL/空值），随即同迁移内 drop `users.api_key` 列——保证"列消失时回填必已完成"的原子顺序，避免两迁移间的中间态。哈希算法与 platform 侧 `api_keys` 写入完全同源（实现时从现有 key 创建路径提取共用函数，杜绝两处哈希实现漂移）。`migrate_api_keys()` 工具因此退役删除。

**D3：`create_user` 返回形态——`User` 去 `api_key` 字段，明文经独立返回值交付一次**
明文只在创建时刻存在于返回值（如 `(User, plaintext_key)` 或等价形态，apply 时对齐调用方最小改动），admin CLI 打印行为不变。`_FULL_COLS` 去列，`get_legacy_api_keys` / `_get_by_legacy_key` 删除。

**D4：rename 三件套直接删除，不留"抛 NotSupported"的空壳**
`rename_agent` / `agent_admin_store.rename` / console 死桩全删——保留抛错壳子只会诱导将来"接通"它；spec 的不可变性 requirement + 守护测试（无 rename 写路径）是更强的防回潮。改名诉求的正路（建新 agent + 显式迁移）写进 spec。

**D5：合并为一个 change 的理由**
两件事同属"管理库身份/标识卫生"（与 schema-residue-cleanup / mgmt-store-hygiene 同族第三批），改动面无交集但审查上下文相同；拆开只多一轮 worktree/归档开销。

## Risks / Trade-offs

- [存量部署有用户正用 legacy key] → 回填保留原 key 可用（哈希后同值可认证），用户无感知
- [哈希实现与 platform 侧不一致导致回填 key 认证失败] → D2 强制共用同一哈希函数 + 升级路径集成测试（旧库带明文 key → 升级 → 原 key 认证成功）
- [User dataclass 去字段牵连面大] → 全仓 grep `\.api_key` 收尾清零；改动集中在 user_store / admin CLI / 测试
- [某处仍依赖 rename] → 删除前全仓 grep 调用方（已知仅 console 死桩与测试）；发现真实消费即上报再定
- [standalone 部署的库没有 `api_keys` 表] → standalone 的本地库同样经 Alembic 建 schema（fleetent-admin 初始化路径），表存在；apply 时以"无 platform 进程 + 本地库"集成测试确认

## Migration Plan

Alembic 新迁移（回填 + drop 列，原子顺序）；代码与迁移同 change 落地。回滚：迁移有 downgrade（重建空列，不还原明文——明文不可逆是设计意图）；代码 revert 即回旧行为（但旧列已空，故回滚需配合库重置——上线前窗口可接受）。

## Open Questions

（无——A/B 取舍与合并打包已与用户对齐。）
