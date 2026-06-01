# fleetent 1.0 设计文档

## 这是什么

本目录是 fleetent 1.0 的设计与验收文档，供团队 review 和分工使用。

每份 capability 文档定义**做什么**和**如何验收**，具体实施通过 OpenSpec 工作流完成。

## 文档结构

```
docs/
  README.md                       ← 本文件：导航 + 写作规范
  strategy.md                     ← 战略背景：为什么做、卖什么、与竞品的差异
    architecture.md                 ← 总体架构：系统定位、模块关系、数据流、关键决策
  capabilities/
    _template.md                  ← 能力域文档模板（新建时复制）
    intelligence-roadmap.md        ← 常乐负责模块的能力地图、MVP 缺口、实施批次
    agent-runtime.md              ← 核心循环、工具、Skill、MCP、沙箱
    im-gateway.md                 ← Slack / Telegram / WhatsApp 接入
    memory.md                     ← 记忆系统、自进化
    scheduling.md                 ← Cron、Webhook
    governance.md                 ← 权限审批、工具白名单、agent 定义
    platform.md                   ← 用户管理、API 认证、admin CLI
    observability.md              ← 评估日志、数据统计、链路追踪
    deployment.md                 ← on-premises 打包、配置
```

## 写作规范

**功能描述**：「现状」和「规划中」每条只写可观察的行为，不写内部实现细节。有必要时加子 bullet 补充边界和约束。

**模块归属**：每份 capability 文档应声明 owning package、public API、owned tables、config namespace
和 cross-module dependencies。没有持久化或配置时写「无」，不要省略。

**验收标准**：只写用户或调用方能观察到的行为（端到端视角）。单元级断言写在 OpenSpec 的测试任务里，不在这里。

**漂移处理**：实施过程中设计有变化，同步更新文档对应 section。文档是活的，不是归档记录。

**版本迭代**：`规划中（vX.X）` 的条目实现后移入「现状」并打 ✅，进入下一版本时将 section 标题改为新版本号并添加新条目。历史版本通过 `git tag` 查看，无需维护多份文档。
