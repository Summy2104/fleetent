# reflection

> 写作提醒：功能描述只写可观察的行为，不写内部实现细节。验收标准只写端到端可验证的行为。

## 概述

系统自我改进机制，定期分析 agent 执行历史，优化记忆质量、改进 skill、并识别知识库缺口。

**负责**：读取 traces 发现规律、清理/合并低质量记忆、生成或改进 skill、上报知识库问题。

**不负责**：实时处理（异步定期触发，不在请求链路上）、skill 的运行时注入（→ agent-runtime）、修改知识库文档内容（只上报，不写回）。

**三个作用目标**：
- **memory reflection**：per-user，优化 memory_layer 中的记忆质量
- **skill reflection**：per-agent，基于 traces 生成或改进 skills/
- **knowledge base reflection**：per-tenant，观察知识库使用质量，上报缺口与问题，不自动写回

**调用关系**：
- 依赖：traces.jsonl（情节记忆数据源）、memory_layer（读取与写回）、skill_registry（读取现有 skill）、knowledge_base（只读，查询召回质量）、permission_gate（prod 环境 skill 变更审批）、config
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

- [ ] **knowledge base reflection**：观察知识库使用质量，只上报不写回
  - 知识空白检测：用户频繁提问但召回质量差 → 上报"该类内容可能缺失"
  - 陈旧内容检测：某些 chunk 长期未被召回，或与近期对话明显矛盾 → 标记待管理员审查
  - 高频共现提示：多个文档频繁被一起召回 → 建议管理员补充整合文档
  - 所有 knowledge base reflection 结果均以建议形式输出，执行由人决定

- [ ] **生效机制**：按作用目标和环境区分
  - memory reflection：直接写回（自动维护）
  - skill reflection：dev 直接写入，prod 走 permission_gate 审批
  - knowledge base reflection：仅上报，永远不自动写回

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

## 验收标准（补充：knowledge base reflection）

**场景 5：知识空白上报**
- Given：用户连续多次提问某类话题，knowledge_base.search() 返回的 chunk 相关度持续低于阈值
- When：knowledge base reflection 定期任务触发
- Then：生成一条上报记录，注明话题类型和问题频次，管理员可查看

**场景 6：陈旧内容标记**
- Given：某个 chunk 在过去 N 天内从未被召回
- When：knowledge base reflection 定期任务触发
- Then：该 chunk 被标记为"待审查"，管理员可决定保留或删除，知识库内容本身不被自动修改

## 待决问题

- [ ] 触发频率：三个 reflection 分开调度，还是同一个 cron job 按序执行？（负责人：待认领）
- [ ] skill reflection 触发条件：需要多少条 traces 样本才触发一次分析？（负责人：待认领）
- [ ] skill 变更提案存储：复用现有 permission_gate 表，还是单独的提案表？（负责人：待认领）
- [ ] knowledge base reflection 上报的输出形式：写入独立日志表，还是通过 IM 通知管理员？（负责人：待认领）
