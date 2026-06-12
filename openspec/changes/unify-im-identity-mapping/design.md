# unify-im-identity-mapping Design

## Context

`im_gateway/access.py:70` 的 `resolve_identity(platform, platform_user_id)` 直接返回原生 id（"no platform DB read"），slack.py（2 处）与 telegram.py 全部收口在此函数。`im_users` 映射（`platform.im_gateway_management.identity.get_or_create(owner_id, platform, platform_user_id)`）现仅 admin CLI / user admin API 消费；该函数既有语义＝首见自动建 `users` 行 + `im_users` 行（`allowed=1`，准入由频道白名单管，见 identity.py:78 v1.0 注释）。注入先例：`user_store.set_api_key_resolver`（`server.py:98` 注入，standalone 留 None）——managed 模式 agent runtime 与 server 同进程，callable 注入可行已被证明。

与用户对齐的决策：A 案（edge 归并）+ A1（首见自动建，身份同一性与准入解耦）。

## Goals / Non-Goals

**Goals:**
- managed 模式下 IM 与 bearer 两条入口解析出同一命名空间的 `Principal.user_id`（内部 `users.id`），agent 侧数据按人归并
- `im_users` 回归"归并真相源"本职
- standalone 行为零变化（恒等透传原生 id），且有守护测试锁死
- 边界显式化：写 platform 身份表的动作只发生在注入的 platform 代码内

**Non-Goals:**
- 不改准入策略（频道白名单照旧；不启用 per-user pending/approve 流）
- 不迁移存量数据（已写入的原生 id 行作历史沉淀；上线前窗口）
- 不修 `platform.im_gateway_management.identity` 的 `_init_db` 双权威残渣（另立小切片，blocklist 同款模式）
- 不动 HTTP/TUI bearer 路径

## Decisions

**D1：注入点形态 = 模块级 setter（仿 `set_api_key_resolver`），不走构造参数**
渠道 handler（Bolt/PTB 回调）创建链路深，构造注入要穿多层；模块级 setter 与既有先例一致、standalone 缺省即透传。resolver 类型：`Callable[[str, str, str], str]`（owner_id, platform, platform_user_id → internal user_id）。docstring 写明：resolver 归 platform 拥有、允许写 platform 身份表、agent 侧不得感知实现与表结构。

**D2：`resolve_identity` 扩展可选 `owner_id` 参数（默认 `"default"`），调用方传 connector 身份**
`get_or_create` 需要 `owner_id`（connector 归属）。slack/telegram handler 各自知道连接器 id，调用处补传；未传时 `"default"` 兜底（单连接器部署）。`resolve_principal` 同步透传。向后兼容：参数可选，既有测试不破。

**D3：tenant 校验放 resolver 包装层（platform 侧），不放 agent 模块**
server.py 注入的包装函数在 `get_or_create` 返回后比对 `user.tenant_id` 与 connector edge 配置 tenant，不一致即抛出标记异常 → handler 拒绝该消息并记日志。校验逻辑属 platform 域，agent 模块只看到"解析失败"。否决放 access.py：agent 模块不应知道 tenant 归属规则。

**D4：首见自动建（A1），不做 pending 回落（A2）**
A2 会让"批准前数据"挂在原生 id 下，批准后又切到内部 id——正是本 change 要消灭的分裂。准入与同一性解耦：身份从第一条消息归并，能不能对话由频道白名单决定（既有 v1.0 语义，零新策略）。

**D5：cron 存档复检语义自然升级，不需要代码改动**
A1 后 managed 模式 IM 创建的 `scheduled_tasks.user_id` 是 `users` 表中的真实用户 → identity-port 既有"平台用户复检"分支自动生效（blocked 则拒），比现状（原生 id 走"渠道担保放行"分支）更严格且符合预期；standalone 仍走渠道担保/无用户管理放行分支。spec 无需改，apply 时用测试确认两分支行为。

## Risks / Trade-offs

- [首见即建 users 行，垃圾/误触消息也会注册] → 频道白名单先于身份解析拒掉未准入频道；只有 allowlist 内频道的真实用户会触达 resolver。可接受
- [resolver 在消息热路径上同步查库] → `get_or_create` 单行索引查询 + WAL，开销可忽略；如将来成为瓶颈可在包装层加进程内 LRU（不在本 change）
- [同名 setter 在测试间泄漏全局状态] → conftest fixture 重置（与 `set_api_key_resolver` 测试处理一致）
- [`im_users` UNIQUE 约束是 `(owner_id, platform, platform_user_id)` 还是 `(platform, platform_user_id)`] → apply 时核实实际索引；canonical spec 写的是后者，若实际带 owner_id 维度，同一渠道用户经两个 connector 进入会建两个映射——如发现此情况，按"同一 (platform, platform_user_id) 复用同一 user"的语义处理并在 spec 复核中确认

## Migration Plan

无 schema 迁移。部署即生效（platform 重启注入 resolver）；存量原生 id 数据不回填。回滚＝去掉 server.py 注入一行（行为退回透传）。

## Open Questions

（无——A/A1、tenant 校验、不迁移存量均已与用户对齐。）
