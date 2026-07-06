# 变更:Slack 取不到用户身份时拒绝,而非伪造 "unknown" 用户

母文档:`docs/records/aaa-8204-recovery.md`(问题 ①,AAA-8204 真因候选)

## 为什么

DM 主动推送被 `你还没有权限使用此 bot,请联系管理员审批` 拦截。该串**只**来自访问门 `_REJECTION_MSG`(`src/fleetent/im_gateway/normalizer.py:24`,553/557/566 调用),且门**只看** `(chat_type, channel, user_id, 配置)`,**与正文无关**。

已确诊(同账号、同 alpha 私聊,"你好"通、复现提示词不通):

- `slack.py:457`(Assistant 面板 `_route_assistant_message`)/`:597`(频道 `_handle`)在取不到 `user` 且 `context.user_id` 为空时,字面量回退 `slack_user_id = "unknown"`。
- `access.resolve_identity("slack","unknown",…)` **不拒绝反而自动建号**:管理库 `im_users` 出现 `slack:unknown`=`43d80443`(2026-06-30 08:36:50 建)。
- 该 id 不在 alpha `allow_users`(实测 `access.user_allowed` 返回 False)→ 门拒绝 + `add_pending`(物理证据:`43d80443` 躺在 alpha 的 `im_approvals.json` pending)。
- 诱因:同 DM `D0BDQ24RRJ8` 反复 `slack_assistant_status_failed … invalid_thread_ts`——**Assistant 线程上下文坏**,而 `context.user_id` 正是从该上下文取,坏了即 None。

净效果:**合法授权用户的消息偶发丢失身份 → 被随机挡在门外**,失败原因对用户不透明(正是 ticket 描述)。

## 改动

1. **不得**把"取不到真实 Slack user"回退成可建号的 `"unknown"` 并送进门:取不到时应**拒绝/丢弃该事件并 warning**(复用既有 `IMIdentityResolutionError` 路径,`slack.py:460` 已有先例),而不是伪造身份。
2. `resolve_identity` 对空 / `"unknown"` 等非真实 platform_user_id **不自动 provision**(防幽灵用户;注意别影响正常用户的首次建号)。
3. 修 Assistant 面板取 user 的来源(从正确字段取,或重建/校正线程上下文),消除 `invalid_thread_ts`,使 `context.user_id` 稳定可得。**先由服务器侧 debug 探针确定真实 payload 形状再动手。**

## 模块边界影响

- **owning package**:`im_gateway/`(`slack.py`、`access.py`)。`im_gateway` 是 no-platform-import edge face,身份 resolver 由 node 注入,本变更不得新增反向依赖。
- **public API surface**:`resolve_identity` 语义收紧(空/unknown 不建号)——需评估对其它连接器的影响,加测覆盖正常 provision 不被误伤。
- **owned tables**:无新表;`im_users` 幽灵行清理 = **服务器侧数据运维**,走平台 API,不在代码里删。
- **config namespace**:无变更(沿用 `im.slack.access`)。
- **cross-module dependencies**:无新增。
- **migration / shim**:无。

## 分工

- **服务器(我)**:**先**加 2 行 debug log(`slack.py:457/597`)打印原始 `payload` keys + `context.user_id` + 解析结果,重启 node,采集真实 assistant `user_message` 事件,定位 user 到底在哪/为何 None;修复上线后验收;清理 `slack:unknown` 幽灵用户(走 API)。
- **本地(你)**:按探针结果改 user 提取 + `resolve_identity` 不建 unknown/空 + 单测(见 tasks.md)。

## 验收

同账号同 DM 连发多条(含带链接/@提及的长消息)都稳定解析成本人、过门;系统不再新增 `slack:unknown`;取不到 user 的异常事件被显式拒绝并告警,而非静默伪造身份。
