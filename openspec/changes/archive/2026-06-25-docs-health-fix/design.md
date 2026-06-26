## Context

2026-06-25 文档全面审计发现 9 类问题：命名漂移、架构说明缺口、路线图进度滞后、archive 标注缺失。所有问题均为纯文档层面，不涉及代码或 spec 级别变更。

## Goals / Non-Goals

**Goals:**
- 消除 shared_memory → agent_memory 命名漂移（涉及 1 个能力文档）
- 补充 3 个架构说明缺口（im-gateway managed 模式、directed-reach delivery queue、scheduling webhook 现状）
- 更新 platform.md v1.0 状态描述
- 刷新 5 个路线图文档的执行进度（Pilot 期）
- 补充 2 个运维文档的 node 相关检查项
- 为 archive/ 下旧文件添加"历史记录"标注

**Non-Goals:**
- 不修改任何 spec 文件（`openspec/specs/`）
- 不修改源码或测试
- 不重构文档结构或目录布局

## Decisions

**D1：就地修改，不移动文件**
archive/ 下文件已在正确位置，只需添加标注头，避免 git history 断裂。

**D2：路线图只标注状态，不删除预测内容**
保留历史规划节点作为决策轨迹，在顶部或相关条目旁追加"✅ 已落地"/"⏳ 延期"标记，不重写内容。

**D3：archive 标注统一格式**
在文件最顶部插入一行：
```
> **[历史记录]** 本文档为过程产物，内容以落地代码和当前架构文档为准。
```

## Risks / Trade-offs

- [路线图状态判断主观] → 仅标注已确认落地的功能（有 commit 或 memory 记录），不确定的保持原状不改。
- [archive 标注可能遗漏] → 按审计清单逐一处理，不做目录级批量替换。
