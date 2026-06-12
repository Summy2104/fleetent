# Tasks — conversation-address-unification

> 每个实现任务严格 TDD：先红后绿。纯数据类/序列化 = unit；涉及 session 文件/恢复链路/适配器协作 = integration。

## 1. 地址数据类与工厂

- [ ] 1.1 测试：`ConversationAddress` 数据类（构造/frozen/dict 序列化往返）+ cron origin dict → 同构解析（行为不变）——unit，先红
- [ ] 1.2 实现：`outbound.py` 新增 dataclass 与 origin 解析收敛——绿
- [ ] 1.3 测试：`make_replier`（携带 thread/blocks 透传/平台分派经 send_to）与 `make_uploader`（thread 文件投递经 send_file_to）——unit（mock connector），先红
- [ ] 1.4 实现：两个工厂函数——绿

## 2. 挂起持久化

- [ ] 2.1 测试：pending 条目含 `address` 与 SessionContext 路由字段（chat_type/thread_root）；旧条目（无 address）读取不崩——integration，先红
- [ ] 2.2 实现：loop 挂起条目增加 address（从 NormalizedMessage/session_context 构造）+ session manager 序列化兼容——绿

## 3. 入站与恢复入口改造

- [ ] 3.1 测试：入站 handler 经工厂构造 reply/upload（行为与现状等价：thread 回复、上传到原 thread）——integration，先红
- [ ] 3.2 实现：slack.py / telegram.py 入站路径接工厂，删除手拼闭包——绿
- [ ] 3.3 测试：`_resume_pending_in_session` 透传 upload_func；continue_run 携带完整投递上下文——integration，先红
- [ ] 3.4 实现：normalizer 恢复路径增加 upload_func 与还原 SessionContext——绿
- [ ] 3.5 测试：按钮恢复（handle_approval_action）从持久化 address 重建 _reply/resume_msg（thread 保真、upload 非缺失）——integration，先红
- [ ] 3.6 实现：按钮路径改造——绿
- [ ] 3.7 测试：文本 approve 路径位置无关（顶层发 approve，输出回原 thread）——integration，先红
- [ ] 3.8 实现：文本路径改造（用 pending address 而非 msg 上下文）——绿

## 4. 等价契约测试集

- [ ] 4.1 实现参数化契约测试：三入口（按钮/文本/重启模拟）× 四断言（回原 thread / upload 可用指向原地址 / progress 可用 / chat_type 保真）+ 缺失地址降级（warning + 触发者上下文）——integration，先红后随实现转绿
- [ ] 4.2 实现：补齐契约缺口直至参数化集全绿

## 5. 收尾

- [ ] 5.1 `make test-pr` 全绿 + integration 对照 main 无新增失败 + mypy 无新增错误
- [ ] 5.2 真机验证：my-bot 重放事故场景——thread 内触发审批→顶层/按钮两种方式批准→回复与后续提示均回原 thread；追问不再分裂新会话
