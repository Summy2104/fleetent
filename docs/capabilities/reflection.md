# reflection

> 写作提醒：功能描述只写可观察的行为，不写内部实现细节。验收标准只写端到端可验证的行为。

## 概述

系统自我改进机制，定期分析 agent 执行历史，优化记忆质量并改进 skill。

**负责**：读取 traces 发现规律、清理/合并低质量记忆、生成或改进 skill。

**不负责**：实时处理（异步定期触发，不在请求链路上）、skill 的运行时注入（→ agent-runtime）。

**两个作用目标**：
- **memory reflection**：per-user，优化 memory_layer 中的记忆质量
- **skill reflection**：per-agent，基于 traces 生成或改进 skills/

**调用关系**：
- 依赖：traces.jsonl（情节记忆数据源）、memory_layer（读取与写回）、skill_registry（读取现有 skill）、permission_gate（prod 环境 skill 变更审批）、config
- 被依赖：cron_scheduler（定期触发）

## 现状

尚未实现。

## 规划中（v1.0）

- [ ] **memory reflection**：定期清理与合并 per-user 记忆
  - 清理过期 context 类记忆（超过 TTL 且未被再次提及）
  - 合并语义重复条目
  - 修正已知冲突（比较 identity / preferences 类条目间的矛盾）

- [ ] **skill reflection**：分析 per-agent traces，生成或改进 skill
  - 发现高频重复的 prompt pattern，提炼为新 skill
  - 识别现有 skill 的低效用法，生成改进版本
  - 可创建新 skill，也可修改现有 skill

- [ ] **生效机制**：按环境区分，预留扩展点
  - dev 环境：直接写入生效
  - prod 环境：生成变更提案，走 permission_gate 审批后生效

## 验收标准

**场景 1：过期记忆清理**
- Given：用户有一条 context 类记忆超过 TTL，且近期对话未再提及
- When：memory reflection 定期任务触发
- Then：该记忆从存储中移除，后续检索不再返回

**场景 2：冲突记忆合并**
- Given：用户记忆中存在两条语义矛盾的 identity 条目
- When：memory reflection 定期任务触发
- Then：两条合并为一条，保留更新的信息

**场景 3：skill 改进提案生成（prod）**
- Given：某 agent 的 traces 中反复出现同类任务模式
- When：skill reflection 定期任务触发
- Then：生成一条 skill 变更提案，状态为 pending；管理员 approve 后 skill 更新生效

**场景 4：skill 直接生效（dev）**
- Given：dev 环境，skill reflection 识别到可改进的 skill
- When：skill reflection 定期任务触发
- Then：skill 文件直接更新，无需审批

## 待决问题

- [ ] 触发频率：memory reflection 和 skill reflection 分开调度，还是同一个 cron job？（负责人：待认领）
- [ ] skill reflection 的触发条件：需要多少条 traces 样本才触发一次分析？（负责人：待认领）
- [ ] skill 变更提案的存储和审批界面：复用现有 permission_gate，还是单独的管理界面？（负责人：待认领）
