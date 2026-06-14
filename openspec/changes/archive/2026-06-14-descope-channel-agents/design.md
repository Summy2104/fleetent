# 设计：descope-channel-agents（IM 访问模型阶段 1）

## D1 — 为什么是死表（端到端确认）

`channel_agents` 所在的"文件绑定路由"子系统全链已死：
- **runtime**：`normalizer.get_agent_for_context` 返回 default、明文 "Bindings-based routing has been removed"；agent 身份由连接器连接（bot 凭据）决定。
- **materialize**：不读 `channel_agents`（也不生成 agent file `bindings.channels`）。
- **列**：`bound_version_id` 无 FK，唯一 reader `get_channel_bound_version_id` 无生产调用。

删表零运行时风险。

## D2 — 窄边界（与阶段 3 的分工）

`channel_agents` 与一个更大的死子系统纠缠（DB 表 + agent.yaml `bindings.*` + 查找顺序 spec）。一次清光会和**阶段 3**（装 connector=agent + chat_type 闸的新路由模型）大面积重叠。故切分：

- **阶段 1（本 change）**：表 + DB 侧消费者（store/CLI/admin 端点/archive 保护）+ **表直接绑定的 spec**（channel-agent-binding / agent-admin-api channel 端点 / agent-admin-ui deploy / agent-definition FK 列 / clone / toggle 的 channel_agents 引用）。
- **阶段 3**：agent.yaml `bindings.channels/users` + `default-agent` 查找顺序 + `Agent lookup priority order`——这套"文件绑定路由模型"在新模型落地时一并重写。

**接受的暂态**：阶段 1 后 default-agent 等 spec 仍提"channel binding"（已死、无 DB 背书），阶段 3 收口。这是有意的切片边界，非遗漏——proposal 已写明。

## D3 — downgrade

`DROP TABLE` 不可逆数据；downgrade 重建**空表** schema（含 `bound_version_id` 列 + UNIQUE(platform,channel_id) + FK→agents.id CASCADE）以保 schema 可逆，不恢复行（pre-launch 窗口可接受）。

## D4 — archive 保护语义微调

`agent_admin_store.references()` 现查 user_agents + channel_agents 保护 archive。去掉 channel 检查后，archive 仅按 user 绑定 + default 阻挡。user_agents 仍在（阶段 2 才 repurpose），其保护不变。toggle/clone 同步去 channel_agents 引用。

## D5 — 迁移编号

append after 真实 head（propose 时 086 → 087，**勿硬编码** down_revision，apply 前 pull 确认；若被占则顺延）。
