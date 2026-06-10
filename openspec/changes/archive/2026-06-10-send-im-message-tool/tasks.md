## 1. ToolContext 扩展（tools/registry + runtime/loop）

- [x] 1.1 Write failing tests: `ToolContext` 含 `outbound_connectors` 字段（默认空 dict）；`loop.run()` 构造的 ToolContext 携带传入的 outbound_connectors（两处构造点经 run 路径覆盖）
- [x] 1.2 Implement field + run() 路径传参 to pass tests

## 2. send_im_message 工具（tools/builtin_tools）

- [x] 2.1 Write failing tests: 注册为 medium；DM 路径调 send_to(platform, connector, target, text)；channel 路径 target_type 透传；platform 留空取 session_context.platform；无连接器返回说明文本；is_reachable False 返回说明文本且不发送；send_to False 返回失败文本
- [x] 2.2 Implement `send_im_message` to pass tests

## 3. 收尾

- [x] 3.1 更新 `docs/approval-and-outbound-decisions.md`（Change 3 决策，含 D2 设计修正：放弃按目标分流的理由）
- [x] 3.2 受影响层收尾：`make test-pr` 全绿；`uv run pytest tests/integration -q` 对照基线无新增失败
- [x] 3.3 本地 my-bot 实机 smoke：配置 allowed_tools + approval_routing(requester)，Slack 私聊让 agent 给本人发 DM，验证审批按钮 → 点击批准 → 消息送达（手动，不进测试）
