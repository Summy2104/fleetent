# 设计：add-agent-im-access（IM 访问模型阶段 2）

## D1 — 三类配置项的归宿（已定）

| 配置项 | 载体 | 为什么 |
|---|---|---|
| 用户准入 | **`user_agents`（保留不改名）** | 跨平台、agent 级、非 IM 专属——不加 im 前缀；表已存在、形状对、有 admin 端点 + references() 集成，零 churn |
| 能力 supports_dm/groups | **`agents` 两列** | agent 级**策略立场**、非版本化推理配置；并入 agents 的 allowed_skills/features/plugins 族；落 agent_versions 会引入"回滚版本→IM 能力变"的意外耦合 |
| 群白名单 | **`agent_im_groups`（新建）** | 群 id 平台特定（Slack channel / Telegram chat），是 IM 概念——带 im 前缀名副其实 |

## D2 — 脚手架边界（与阶段 3 的分工）

本阶段只立"**可配置的存储**"：表、列、admin 端点。**runtime 不消费**——materialize 读这些写进 agent.yaml `im` 块、准入闸按 chat_type 分流、默认关的强制，全在**阶段 3**。

故本阶段 spec 的 scenario 只断言"**存储 + admin 配置**"层面（admin 设群白名单 → agent_im_groups 有行；设能力 → agents 列变），**不断言运行时效果**（那是阶段 3）。这是有意的脚手架切片——让管理面先就位、可独立测试，runtime 接线随后。

## D3 — 默认全关

`supports_dm`/`supports_groups` 列默认 `0`；`agent_im_groups` 默认无行。即新建 agent 在阶段 3 闸落地后**默认谁都用不了、哪个群都不进**，须显式配置开启（安全默认）。本阶段只保证默认值正确，强制在阶段 3。

## D4 — 迁移

append after 真实 head（propose 时 087 → 088，**勿硬编码** down_revision）。`CREATE TABLE agent_im_groups`（FK→agents.id ON DELETE CASCADE，遵 identity-model）+ `ALTER TABLE agents ADD COLUMN`（两列、`ADD COLUMN` 无需重建 agents、避开 11 子表 FK 重建风险）。downgrade 反向 drop 列 + drop 表。

## D5 — 命名

- 用户准入：`user_agents`（不动）。
- 群白名单：`agent_im_groups`（agent_id, platform, group_id）。
- 能力：`agents.supports_dm` / `agents.supports_groups`。
- 与 agent_kbs/agent_mcp_servers 的 `agent_<物>` 绑定表风格一致。
