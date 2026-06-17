# Design — fix-send-im-channel-self-dm-routing

## 问题精确化

`send_im_message(target, text, target_type, platform, files)` 现状（`builtin_tools.py` ~829-913）：

1. 文本投递：`outbound.send_to(platform, connector, target, text, target_type=target_type)`（~869）。
2. 文件投递：`outbound.send_file_to(platform, connector, target, host)`（~898）——注意**未传 `target_type`/`thread`**。
3. 审批判级在 `approval_policy.risk_for("send_im_message", {target,target_type}, ...)`：当 `(target,target_type)` = 当前会话地址 → `none`。

缺陷三角同时成立才触发：**(a)** 入站是频道会话；**(b)** `target == 发起人`；**(c)** `target_type == "user"`。此时审批轴判为"当前会话"（免审），可 `target_type="user"` 使投递面变成发起人 DM ≠ 频道线程。

`send_file`（~998-1012）对照：recipient 取 `conversation_address.{chat_id,target_type,thread_id}`，所以频道会话必落频道线程。本 change 让 `send_im_message` 在上述三角下与 `send_file` **同面投递**。

## 决策

### D1. 在哪里改写：投递前的目标解析，而非审批层
审批口径**保持不变**（当前会话→`none` 是正确的：发给发起人本就该免审）。要改的只是**投递面**。因此在 `send_im_message` 计算实际投递目标处插入一次"自我 DM→会话钉定"改写：命中三角时，用 `conversation_address` 覆盖 `(recipient, target_type, thread)`，其余分支保持原 `target`。

### D2. 用纯函数承载决策，便于 unit 隔离测试
新增模块级纯函数：

```python
def _resolve_self_dm_redirect(
    target: str, target_type: str, address: Any, sender_id: str
) -> dict[str, Any] | None:
    """命中"频道会话中对当前发起人的 user-DM 投递"时，返回钉回当前会话的投递覆盖
    {"recipient": <chat_id>, "target_type": "channel", "thread": <thread_id>}；否则 None。

    判据（全满足才改写）：
      - address 存在且 getattr(address, "chat_type", "") == "channel"
      - target_type == "user"
      - target == sender_id（去空白；两侧非空）
    """
```

- **只读入参、无 I/O**：unit 层用 `types.SimpleNamespace` 造 `address` 即可红/绿，符合仓库 unit 边界（不碰真实 DB/store/HTTP）。
- 频道判定用 **`chat_type == "channel"`**（可靠字段），**不依赖 `address.target_type`**——后者在 `im_gateway/slack.py` 被硬编码为 `"channel"`（latent，与 `chat_type` 矛盾时不可信），属另案，本 change 规避而非顺手改它（保持 scope 收敛）。
- 改写后 `target_type` 显式置 `"channel"`（因已知 `chat_type=="channel"`），`recipient=address.chat_id`，`thread=address.thread_id`。

### D3. 透传 `target_type` 与 `thread` 到**两条**投递分支
现状文件分支（~898）未传 `target_type`/`thread`。命中改写后，文本与文件都必须落同一频道线程，故：
- 文本：`outbound.send_to(..., recipient, text, target_type=eff_target_type)`
- 文件：`outbound.send_file_to(..., recipient, host, target_type=eff_target_type, thread=eff_thread)`

其中 `eff_*` 来自改写结果（命中）或原值（未命中，保持当前行为）。需确认 `outbound.send_file_to` 已支持 `target_type`/`thread` 关键字（`send_file` 已这样调用，应已支持）；若签名不支持则在 outbound 侧最小补齐（仍属本 change 受影响面，记入 tasks 核实）。

### D4. footer / delivery-receipt 不变
改写只改投递目标，不改 `_record_delivery` 调用结构。命中后 receipt 的 `target` 自然变成频道 id，footer 即显示 `（C09…37V）` 而非 `（U09…R25）`——这恰是修复后的期望可观测信号，无需额外改 `traces.py`。

## 不做 / 显式 de-scope
- **方案B（升级审批）**：不采用——发给发起人本属当前会话，强制审批体验过重。
- **③ `generate_image` 默认投递**：不做——① 落地后，任何工具产物经 `send_im_message` 的"自我 DM"都已被钉回会话，③ 冗余。
- **`im_gateway` 的 `conversation_address.target_type` latent bug**：不在本 change 修；本 change 仅依赖 `chat_type`，不被该 bug 影响。

## 风险与回归边界
- **唯一行为变化**：频道会话里"发给发起人本人的 user-DM"——从落 DM 改为落频道线程。**给他人外发、纯 DM 会话、频道→频道外发**均不受影响（纯函数对这些返回 None）。
- **潜在用户可感知影响**：用户在频道里若*确实*想要 agent 私信自己（如"别发频道、私信我"），本 change 会把它落回频道线程（方案A 的已知代价，已与用户确认接受）。
- 回归验证：unit 覆盖纯函数全分支；integration 覆盖"频道会话 + 发起人 user 投递 → 落频道线程"端到端，并断言"他人外发仍走 DM 且仍 medium"。
