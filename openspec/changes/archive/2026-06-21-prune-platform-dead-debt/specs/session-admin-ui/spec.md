## REMOVED Requirements

### Requirement: Chat playground

**Reason**: 该 requirement 要求控制台经 `/admin/chat/start`、`/admin/chat/{session_id}/message` 提供内嵌试聊，但平台 server 从未实现 `/admin/chat/*` 路由（唯一的裸 `/chat` 在节点侧 agent 运行时 app，非平台）。UI 上的对应按钮点击即报错，是坏死功能。

**Migration**: 控制台不再内嵌 agent 试聊；对 agent 的交互式测试改用 `fleetent chat` TUI 或直接对节点上运行的 agent 发起会话。Sessions 治理（接管 / 注入 / 强制结束 / 清空 / 重置）不受影响、继续可用。
