# 变更:审批 resume 路径解析 outbound 连接器(托管模式批准后真正能送达)

母文档:`docs/records/aaa-8204-recovery.md`(问题 ⑥,2026-06-30 实测发现 —— **很可能是 AAA-8204「推送失败」的真正核心**)

## 为什么(实测证据)

`approve ebd2986f` 批准后,resume 执行 `send_im_message`,工具返回:

```
[审批 ebd2986f 已批准,send_im_message 执行结果:
 发送失败:当前通道不支持主动外发(无可用 slack 连接器)。该功能仅在 IM 网关运行时可用。]
```

DB 证实 `ebd2986f` 已 `approved`,但消息没发出。

根因(代码级):
- **正常 turn**在 `runtime/loop.py:1986` 调 `resolve_for_runtime(agent_name, outbound_connectors)`。托管模式下(`is_node_managed_runtime()` 为真且无 live 连接器)它返回 `{platform: ManagedOutboundConnector(agent_name, platform)}`——即 enqueue 到 `im_outbound_queue` → node drain → 送达。所以**未被审批门拦下的 send,在托管模式能发**。
- **但审批 resume** 走 `im_gateway/normalizer.py` 的 `_resume_pending_in_session`,构造 `ToolContext` 时直接用 `outbound_connectors=msg.outbound_connectors`(approve 命令的 `msg` 经 `/im/route` 进来、该字段为空),**从不调用 `resolve_for_runtime`** → 连接器为空 → `connectors.get("slack")` 为 `None` → `send_im_message` 命中 `builtin_tools.py:1174` 的"无可用连接器"分支失败。
- `send_im_message` 是 `medium`、对第三方必经审批 → 必经 resume → 在托管模式**必然**"无连接器"失败。即:**给别人主动发消息,在托管部署下即便批准也送不出去**。这正是工单的「推送失败」。

> 这同时解释了为何之前的复现里"批准了也没送达":不是审批没批,是 resume 后没有可用连接器。`send_file` 的 resume 走同一函数,同样受影响。

## 改动

在 `_resume_pending_in_session` 构造 `ToolContext` 之前,用 `resolve_for_runtime(agent.name if agent else None, msg.outbound_connectors)` 解析连接器(与 `loop.py:1986` 完全一致),再把结果传给 `ToolContext.outbound_connectors`(以及 `make_replier`/`make_uploader` 一并用解析后的值)。

## 模块边界影响

- **owning package**:`im_gateway/`(`normalizer.py` 的 `_resume_pending_in_session`)。
- **public API surface**:无签名变更。
- **复用**:top-level `outbound_connectors.resolve_for_runtime`(非 platform 依赖,loop 已在用)。
- **owned tables / config / migration**:无。

## 分工

- **本地(你)**:在 `_resume_pending_in_session` 调 `resolve_for_runtime` + 单测(`is_node_managed_runtime()` 为真时,resume 的 `ToolContext.outbound_connectors` 含 `ManagedOutboundConnector`;standalone 路径不回归)。
- **服务器(我)**:真实 Slack 验收——发→审批→批准后,**程鑫真的收到**带链接+@提及的消息(node 的 `im_outbound_queue` 有出队投递记录)。

## 验收

托管模式下,经审批 resume 的 `send_im_message`(及 `send_file`)真正投递(enqueue → node drain → 送达),不再返回"无可用连接器";AAA-8204 原始用例端到端成功。
