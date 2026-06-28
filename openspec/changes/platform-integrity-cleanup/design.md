# 设计:平台数据完整性与门控收尾

## Context

三组缺口均已对当前 main head(retire-agent-versioning-and-askit 合入后)复核确认:

- `agent_admin_store.references(agent_id)` 只 `SELECT user_id FROM user_agents`,`channels` 恒返回 `[]`;`agent-lifecycle-toggle` 的"Binding protection before archive"依赖它。
- `node_store` / `placement_store` 中 `unpin_agent` / `deregister_node` 均无 `node_agent_status` 的 DELETE;该表只有 upsert/select。
- `agent_store.get_agent_for_user()` 全仓零非测试调用。
- `vault_provider` / `connectors` 对 `external_services.enabled` 零引用(grep 证)。
- `teams` 主键仅 `(id)`;`agents.team_id` 为单列 FK→teams(id);`api_keys.user_id` 为 `TEXT NOT NULL` 无 FK;`delete_user` 不级联 api_keys。

## Goals / Non-Goals

**Goals:**
- 归档保护覆盖全部引用类型,杜绝"绑着资源仍被静默归档"。
- node 上报态在解绑/注销时确定性清理,消除幽灵 running 行。
- 禁用的外部服务在凭证链被门控(安全)。
- DB 级强制 team↔agent 同租户 + api_keys↔users 完整性。
- 删一处确证的死代码。

**Non-Goals:**
- 不做 status 运行时强制(kill-switch,需决策)。
- 不删那三个带 remove-vs-wire 小决策的死列。
- 不碰 KB worker 托管 / session_meta / skills 治理列 / 任何 UI 重设计。
- 不改任何对外端点签名。

## Decisions

### D1. 三组合一个 change,但分组分别 commit

P1/P2/P3 主题不同但都属"完整性/卫生收尾"、各自小且低风险。合一个 change:① 只产生一条 Alembic 迁移 → 规避并行迁移撞号;② 一个 PR 评审。**纪律**:apply 时 P1/P2/P3 各自独立 commit(`fix`/`refactor` 分别),不混。

- **备选**:拆三个并行 change。**否决(用户决定)**:三组要么纯代码、要么单迁移,合一更省协调;并行的收益(都很小)抵不过三套 propose/apply/PR 开销。

### D2. references() 补全引用集合,保留硬阻断语义

`references()` 增查 `agent_im_groups`/`agent_mcp_servers`/`agent_kbs`/`agent_service_grants`/`agent_placements`,返回结构扩展为按资源类型分组的非空引用;`agent-lifecycle-toggle` 的归档前检查"任一类型非空即 409"。

- **备选**:改为 warn + x-confirm 强制归档。**否决**:超出本 change"无决策"边界,且削弱现有保护;保持硬阻断,仅补全覆盖面。

### D3. node_agent_status 在 mutation 点确定性清理

在 `unpin_agent(agent_id)` 删 placement 时 `DELETE FROM node_agent_status WHERE agent_id=:aid`;在 `deregister_node(node_id)` 时 `DELETE ... WHERE node_id=:nid`。

- **备选**:周期性 GC sweep 对账。**否决**:解绑/注销是确定的触发点,写侧同步删除最简单、即时一致,无需后台任务。

### D4. enabled 门控落在 vault_provider 解析链(单一 choke)

在凭证解析入口(`vault_provider` 的 get/refresh/resolve 路径)读 `external_service_store.get_service(...).enabled`,为 false 时返回"未授权/需 consent"等价结果,**不抛异常打断**调用方(与现有 NeedsConsent 风格一致)。

- **备选**:在 admin 绑定端点拦截(禁用则不能新建绑定)。**否决**:绑定可能先于禁用存在;在解析链门控才能覆盖"已绑定 + 后禁用"的真实场景。两者不互斥,但本 change 只做解析链这一道(最小且全覆盖)。

### D5. P3 迁移:脏数据预扫 → batch 重建 FK

SQLite 改/加外键须 `batch_alter_table`(整表重建)。迁移顺序:
1. **预扫**(见 D6)。
2. `teams` 加 `UNIQUE(id, tenant_id)`。
3. `agents` batch 重建,`team_id` 改为复合 FK `(team_id, tenant_id) → teams(id, tenant_id)`(保留 `ON DELETE RESTRICT`,与现状一致)。
4. `api_keys` batch 重建,加 `FK(user_id) → users(id) ON DELETE CASCADE`。
- downgrade 反向重建(回落单列 FK / 去 UNIQUE / 去 api_keys FK),保持可逆。

### D6. 脏数据策略:孤儿 key 自动吊销,跨租户 team 引用 fail-loud

- **孤儿 `api_keys`**(user_id 指向不存在 user):迁移内 `DELETE`(等价吊销——本就无效),记日志。
- **跨租户 team 引用**(`agents.team_id` 的 team.tenant_id ≠ agent.tenant_id):**不猜、不自动改**,迁移**显式报错并列出违例行**,要求操作员先在管理面修正归属再重跑。理由:team 归属是业务事实,自动改可能掩盖真实数据问题(数据主权场景尤甚)。

- **备选**:跨租户引用也自动置 NULL。**否决**:静默丢 team 归属属隐性数据损坏。

## Risks / Trade-offs

- **[不触发 node 批量 respawn]** 本 change 不改 agent 配置物化(agent.yaml 内容不变),desired-state 哈希不变 → node 不会 respawn 运行中的 agent。(与 retire change 不同,这里无需哈希稳定性验收。)
- **[迁移卡在脏数据]** → D6 预扫:孤儿 key 自动清、跨租户引用 fail-loud 并给出违例清单;迁移前对管理库标准备份。
- **[enabled 门控误伤]** 仅影响 `enabled=false` 的服务(操作员显式意图);已授权但未禁用的服务不受影响。回归测试覆盖"启用→放行 / 禁用→拒绝"。
- **[复合 FK batch 重建]** SQLite 整表重建有数据搬运,迁移测试须在含数据的库上验证(沿用 migration 测试范式),并跑全量 integration(动 schema=跨切面)。
- **[references() 多查 5 表]** 仅在归档这种低频 admin 操作触发,性能无虞。

## Migration Plan

单条 Alembic forward 迁移(106,接 105):预扫(孤儿 key 删 / 跨租户 team 引用报错)→ `teams` UNIQUE → `agents` 复合 FK batch 重建 → `api_keys` FK batch 重建。代码侧 P1/P2 与迁移同 change 落地。回滚:反向迁移重建(已确认可逆);上线前窗口优先前向修复。

## Open Questions

- D6 的脏数据策略(孤儿 key 自动删 / 跨租户引用 fail-loud)是本 change 唯一带轻微取舍的点。若希望跨租户引用也自动归并到 default/agent 自身租户,需在 apply 前改 D6——默认按"fail-loud、人工修"执行。
