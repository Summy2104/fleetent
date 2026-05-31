## 0. 前置确认

- [x] 0.1 确认本 change 只做迁移评估和拆分计划，不实现 knowledge-base 运行时代码
- [x] 0.2 确认本 change 不引入 LlamaIndex、LanceDB、OpenAI Embeddings 或 docling 等依赖

## 1. 盘点 knowledge-bridge

- [x] 1.1 阅读 `../knowledge-bridge/README.md`、`ARCHITECTURE.md`、`docs/DESIGN.md`、`docs/ROADMAP.md`
- [x] 1.2 盘点 `knowledge_bridge/core`、`parsers`、`connectors`、`sync`、`pipeline`、`retrieval`、`metadata`、`audit`
- [x] 1.3 记录关键能力、依赖和 fleetent 适配风险

## 2. 分类迁移资产

- [x] 2.1 输出可直接迁移清单
- [x] 2.2 输出可参考但需重写清单
- [x] 2.3 输出暂缓迁移清单
- [x] 2.4 输出不迁移清单和原因

## 3. 拆分后续 specs

- [x] 3.1 定义 `knowledge-base-core` 最小范围
- [x] 3.2 定义 parser / connector / hybrid search / graph search / sync planner 的后续拆分
- [x] 3.3 标注每个后续 spec 的依赖、风险和不包含范围

## 4. 写迁移计划文档

- [x] 4.1 新增 `docs/knowledge-bridge-migration-plan.md`
- [x] 4.2 更新 `docs/capabilities/knowledge-base.md`，链接迁移计划并说明 knowledge-base 将按拆分 specs 渐进实现
- [x] 4.3 自检文档无 TBD / TODO / 未定责任项

## 5. 收尾验证

- [x] 5.1 运行 `openspec validate 2026-05-31-knowledge-bridge-migration-plan`
- [x] 5.2 运行 `git diff --check`
