# AAA-8204 推送/审批可靠性修复 —— 任务分工与排期

Jira: https://antalpha.atlassian.net/browse/AAA-8204
诊断日期: 2026-06-30(基于**线上安装版**代码 `~/.local/share/uv/tools/fleetent` + 真实 DB + journal 实测）

## 1. 背景:四个叠加问题(已实测确诊)

| # | 现象 | 根因(file:line) | 关键证据 |
|---|------|------------------|----------|
| ④ | agent 反复被强杀(地基,放大其余一切) | `_stop_running`(`runtime/agent_app.py:627`)SIGUSR1 后轮询 30s 等**进程退出**;`_drain_and_close`(`:133`)排空后打 `agent_drain_completed` 但**进程不退出**,扛过 SIGTERM(5s)→ SIGKILL | 17 次重启,15 次 drain 在 ~200ms 完成且 `active_runs=0`,却 17 次全撞 30s `agent_drain_timeout`→`agent_force_kill`;窗口内 `_forward_inbound` 报 `httpx.RemoteProtocolError` 丢入站消息 |
| ① | DM 主动推送被 `你还没有权限使用此 bot` 拦(AAA-8204 真因候选) | `slack.py:457`(Assistant 面板)/`:597`(频道)取不到 `user` 时字面量回退 `"unknown"`;`access.resolve_identity` 反而自动建号→不在 `allow_users`→`normalizer.py:565` 拒+`add_pending` | im_users 第 10 行 `slack:unknown`=`43d80443`(08:36:50 建)、躺在 alpha 的 `im_approvals.json` pending;同 DM `D0BDQ24RRJ8` 反复 `slack_assistant_status_failed invalid_thread_ts`=线程上下文坏→`context.user_id`=None |
| ③ | 手动 `approve <id>` 死循环 | `_LEADING_MENTION_RE=^\s*<@[^>]+>\s*`(`normalizer.py:23`)只剥真正的 `<@id>`;字面量 `@R. Alpha` 剥不掉→`_match_approval_command` 不匹配→落主循环重发 | 实测:`approve <id>`✅、`<@U…> approve <id>`✅、`@R. Alpha approve <id>`✗;ID 链 00b0691a→e0862acb→4a5c0e85 |
| ② | 审批按钮(批准/拒绝/始终允许)全崩 | `handle_approval_action`(`slack.py:222`)→`approval_store.database()` 在 **node 进程** `_state_db is None`(只 `agent_app.py:391` 在 agent boot 接)→`RuntimeError: state_db not initialized`;`ack()` 已发,handler 抛,run 不 resume | journal `state_db not initialized` 栈;按钮点后无 resume |

> resume 路径 `approval_resume.py:102` 是**直接执行工具不再过门**——所以 ③ 一旦命中就不会循环,且会真正送达。

## 2. 环境分工原则

- **服务器(本部署机,有真实数据 / 能 live Slack+journal+DB / 能部署)**:一切**需要真实数据或上线**的事——活体诊断、debug 探针、部署(reinstall+restart)、生产复现验收、真实 DB 清理。
- **本地(开发机,碰不到真实数据,只能 mock/tmp_path 单测)**:一切**纯代码 + 单测/集成测**——四个修复的实现与 TDD(unit 用 mock LLM/DB/HTTP;integration 用 tmp_path,绝不碰 `data/`)。

## 3. 四个变更与分工

| 变更目录 | # | 服务器侧(我) | 本地侧(你) |
|----------|---|----------------|------------|
| `openspec/changes/agent-shutdown-exit-after-drain` | ④ | 活体抓"drain 后不退出"的 hang 源(对真 agent 发 SIGUSR1 + py-spy/faulthandler dump 存活 task);部署;验收重启变 graceful | 写"drain 完成→进程 exit(0)"单测 + 修复关停链 |
| `openspec/changes/slack-identity-reject-unknown-user` | ① | **先**加 2 行 debug 探针抓真实 assistant `user_message` payload+context,定位 user 字段;部署;验收;清理 `slack:unknown` 幽灵用户 | 按探针结果改 user 提取 + `resolve_identity` 不给空/unknown 自动建号 + 单测 |
| `openspec/changes/approval-command-tolerate-text-mention` | ③ | 真实 Slack 验收(打字 approve 不再循环、送达) | 改 `_strip_leading_mention`/`_match_approval_command` + 单测 |
| `openspec/changes/managed-approval-button-wire-statedb` | ② | 真实 Slack 点按钮验收;清理历史卡住 pending(00b0691a 等) | 实现(推荐方案 A:按钮→合成 approve 指令走 `/im/route`)+ 单测 |

## 4. 排期(强依赖,按序推进)

1. **④ 先修先上**(地基)。顺序:服务器活体诊断 → 本地修+测 → 服务器部署+验收。不先修 ④,其余验收都会被 ~35s 下线窗口污染。
2. **① 第二**。顺序:服务器 debug 探针抓 payload(**先于**本地动手)→ 本地修 → 服务器部署+验收+清幽灵用户。
3. **③ / ② 并行收尾**(② 复用 ③ 的命令路径,建议 ③ 先落)。

## 5. 部署步骤(每个变更上线;参考既往部署坑)

合并到 main 不自动生效。每次上线:
```
# 在部署机
uv tool install --reinstall --no-cache <fleetent 包源>
uv run alembic upgrade head          # 若有管理库迁移
systemctl --user restart fleetent-platform.service
systemctl --user restart fleetent-node.service   # node 重启才生效,只重启 platform 不够
```
> node/agent 是 systemd `--user` 服务;agent 由 node 在 reconcile 时拉起。

## 6. 上线前的即时运维(服务器侧,先做)

- 清掉 4 条卡住的 pending 审批(00b0691a / f758a7a7 / 8eafa231 / 305c9a87)与 `slack:unknown`(43d80443)幽灵用户——**走平台 API,不直连 DB**(审计/UI 可见)。
- 临时告诉测试同学:手动审批只打 `approve <id>`(不带 `@R. Alpha`),且别在重启窗口发;别点审批按钮(②未修前会崩)。

## 7. 验收(服务器侧,真实 Slack)

- ④:改一次配置触发重启,journal 出现 `agent_process_exited_gracefully` 而非 `agent_force_kill`;重启期间无 `RemoteProtocolError` 丢消息。
- ①:同账号同 DM 连发多条都稳定解析成本人、过门;不再新增 `slack:unknown`。
- ③:DM/频道用 `@R. Alpha approve <id>` 与 `approve <id>` 都正确 resolve 并送达,不再刷新 ID。
- ②:点三种按钮都能 resolve + run resume + 送达,无 `state_db` 报错。
- 端到端:复现 AAA-8204 原始用例(向 程鑫 发带链接+@提及 的消息)一次成功并送达。

## 8. 2026-06-30 实测更新(探针 + session 取证)

加临时探针(`slack.py:457/597` 打 `im_identity_probe`)重启 node 后,由真实用户(U0B6SU8LH0D)在 alpha DM 复现,结论修正:

- **新增 ⑤(最高优先级)= 工具待审批期间谎报成功**。session 取证:`send_im_message → awaiting_human_approval(ebd2986f)` 挂起后,用户回自然语「同意」(非 `approve <id>`),agent **不调用工具就捏造"已发送成功"**;DB 证实 `ebd2986f` 至今 `pending`、消息从未发送。**这是工单「失败可感知」验收点的反向违反,最危险。** 详见 `openspec/changes/approval-pending-no-false-success`。
- **① 降级为"潜伏/偶发"**。探针证明本次复现身份解析正确(`payload_user/ctx_user_id/resolved` 均 = U0B6SU8LH0D),**未触发** unknown 幽灵用户;① 只在 Assistant 侧边栏线程上下文坏(`invalid_thread_ts`)时偶发。保留修复,但**不是本次复现的拦路虎**,优先级下调。
- **附带配置层问题**:slack-mcp 的 bot 缺 `conversations_join` 的 scope(`missing_scope`),agent 转述成"权限不足,无法加入私信频道"——只是噪音,`send_im_message` 并不需要 join。属配置/agent 行为层,非本批代码变更核心。

### 修订后的优先级
1. **⑤**(谎报成功 / 失败不可感知)—— 最高,本地可立即开始(纯 runtime/loop + 单测)。
2. **②③**(让审批真能批下去:按钮不崩、`@名字 approve` 不循环)。
3. **④**(地基:重启不再 force-kill)。
4. **①**(潜伏)+ slack-mcp scope(配置)—— 收尾处理。

> 注:纯文本 `approve <id>`(不带 @名字)**实测可用**——命中后走 resume 直接执行工具、不再过门。所以"能批下去"的最小可用路径已存在(只是 UX 差);⑤ 才是必须先堵的正确性漏洞。

## 9. 2026-06-30 续:⑥ —— 批准后仍发不出(很可能是「推送失败」真正核心)

实测 `approve ebd2986f`:审批被正确识别、DB 置 `approved`,但 resume 执行 `send_im_message` 返回「发送失败:无可用 slack 连接器,仅 IM 网关运行时可用」,消息没发出。根因:正常 turn 在 `loop.py:1986` 调 `resolve_for_runtime` → 托管模式拿到 `ManagedOutboundConnector`(enqueue→node→送达);但**审批 resume 的 `_resume_pending_in_session`(normalizer.py)没调 `resolve_for_runtime`**,直接用空的 `msg.outbound_connectors` → 连接器为 None → 失败。`send_im_message` 对第三方必经审批→必经 resume→**托管下批了也送不出**。详见 `openspec/changes/approval-resume-resolve-outbound-connectors`。修复:resume 也调 `resolve_for_runtime`。

并存确认:本轮 [9] agent 在用户「同意」时谎报成功(⑤),[11] 真执行失败后**如实**报错——说明真执行路径的"失败可感知"是好的,⑤ 仅在"未执行就续话"时发生。

### 最终优先级(2026-06-30 末)
1. **⑥**(批准后真能送达 = 推送失败核心)
2. **⑤**(未执行不得谎报成功)
3. **②③**(审批 UX:按钮不崩、`@名字 approve` 不循环)
4. **④**(地基:重启不再 force-kill)
5. **①**(潜伏 unknown-user)+ slack-mcp `conversations_join` scope(配置)

> ⑥+⑤ 合起来才闭环 AAA-8204:⑥ 让消息真发出去,⑤ 保证没发出去时不说谎。
