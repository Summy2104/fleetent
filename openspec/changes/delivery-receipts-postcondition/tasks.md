# Tasks — delivery-receipts-postcondition

> 依赖序：在 trace-tool-spans（delivery 事件复用其记录 API）与 unified-file-exchange（send 工具共享投递内核）合入后实施。每任务严格 TDD 先红后绿。

## 1. 回执对象与原语改造

- [ ] 1.1 测试：`DeliveryReceipt` 形状 + `send_to`/`send_file_to` 成功/失败回执（含 Slack ts/file_id 提取、永不抛语义保持）——unit（mock connector），先红
- [ ] 1.2 实现：outbound 返回回执，仓内调用方（send_file/send_im_message/上传原语/cron/_notify_approvers）bool 语境收敛为 `receipt.ok`——绿

## 2. 台账与 trace

- [ ] 2.1 测试：run 级台账收集多次投递（工具/上传混合）；cron `_fire` 路径自建台账；`delivery` trace 事件落库（目标脱敏、写失败仅 warning）——integration，先红
- [ ] 2.2 实现：台账挂 run state/ToolContext 注入 + traces 记录——绿

## 3. 事实尾注

- [ ] 3.1 测试：尾注渲染真值表（成功文件+失败消息混合 / 全成功 / 台账空不追加 / 目标摘要脱敏）——unit，先红
- [ ] 3.2 实现：确定性渲染函数——绿
- [ ] 3.3 测试：收尾注入（非流式回复后拼接；流式结束后独立消息补发；模型文本不可移除尾注）——integration（mock LLM），先红
- [ ] 3.4 实现：loop/normalizer 收尾注入两路——绿

## 4. 收尾

- [ ] 4.1 `make test-pr` 全绿 + integration 对照 main 无新增失败 + mypy 无新增错误
- [ ] 4.2 真机验证：my-bot 重放 AAA-8050 场景——含外发任务的回复带事实尾注；纯问答无尾注；谎报场景（MCP 邮件）尾注不背书
