# 设计：rename-connector-to-im（IM 访问模型阶段 4 · 纯改名）

## D1 — 为什么单列一棒、放最后
阶段 1–3b 功能落地时刻意零改名（把"外科手术式改一个重载词"与大功能改动解耦、降风险）。本阶段是纯机械改名、零行为，独立验证（行为不变 = 测试全绿即证）。

## D2 — 改名映射（权威）
见 proposal「What Changes」表。要点：
- block `connectors:`→`im:`；类 `AgentConnectors`→`ImBinding`、`SlackConnector`→`SlackBinding`、`TelegramConnector`→`TelegramBinding`、`ConnectorAccess`→`ImAccess`；字段 `allow_channels`→`allow_groups`。
- `supports_dm`/`supports_groups`（阶段 2/3 已加，在顶层容器上）随容器改名移到 `ImBinding`。

## D3 — 铁律：只动"IM bot 连接"这一义
"connector" 四义，**只改第一义**：
- ✅ 改：agent.yaml `connectors.slack/telegram` + `ConnectorAccess`/`SlackConnector`/`TelegramConnector`/`AgentConnectors` + 其 IM-gateway 消费方（slack/telegram/supervisors/registry/normalizer/access）+ materialize 写 `im` 块。
- ❌ 不碰：`connector_admin_api`/`connector_config_store`/`connectors` 表（工具 OAuth）；`kb_connector_store`/`kb_connectors`/`knowledge_base/connectors/*`（KB 数据源）；`im_connectors` 表（owner 级，已 im_ 前缀、独立）。
- apply 时**先 grep 区分**：`agent.connectors`/`ConnectorAccess`/`connectors:` block 是目标；带 `kb_`/`oauth`/`connector_admin`/`im_connectors`(表) 的是另三义、跳过。

## D4 — spec 名字同步在 apply 做（不脱离代码预抄）
本 change 的 proposal/design/tasks 定计划；7 个相关 spec 的 `ConnectorAccess`/`connectors.`/`allow_channels` 措辞**在 apply 时与代码改名同一次 find-replace 完成**，再 opsx:archive 同步 canonical。理由：纯改名脱离代码单独抄 7 个 spec 全文 = 高工作量 + 易与代码对不齐 + 零语义价值。apply 会话改完代码后顺手把 spec 名字过一遍即可。

## D5 — 无迁移 / 排序
- agent.yaml = agent 侧配置、`ConnectorAccess` = Python、`allow_channels` = agent.yaml 字段：**无管理库迁移**，不碰 Alembic 链。
- 但 apply **须排在阶段 3b 后**：两者都改 data-model.md（避免并发编辑冲突），且本阶段改的是 post-3b 代码。
- 无别名 shim（pre-launch，破坏 agent.yaml 可接受，重写即可）。

## D6 — 验证
纯改名 = 行为不变。apply 收尾：make test-pr + integration 全绿（无新增失败）即证；外加全仓 grep 确认 IM 义 `connectors`/`ConnectorAccess`/`allow_channels` 已清零、而另三义（tool/KB/im_connectors 表）**完好未动**。
