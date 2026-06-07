## Why

E2E 测试暴露了四个运行时 bug，导致工具调用失效、DB 写入崩溃、skills 无法加载、standalone agent 工具审批死锁。这些 bug 均在已有代码路径中，需在合并前修复以保证基本可用性。

## What Changes

- **`im_gateway/normalizer.py`**：`allowed_tools` 空列表转 `None`，避免 `check_tool_access` 空列表返回 False 屏蔽所有工具
- **`runtime/agent_app.py` (`/chat` 路由)**：同上，`agent.allowed_tools + plugins` 为空时也转 `None`
- **`migrations/versions/060_fix_approvals_id_to_text.py`**：新增 migration，将 `approvals.id` 列从 `INTEGER` 改为 `TEXT`，与 `loop.py` 生成的 UUID 字符串对齐
- **`skills/registry.py`**：`base.rglob("SKILL.md")` 加 `follow_symlinks=True`，支持符号链接目录下的 skills
- **`runtime/agent_app.py` (approval 端点)**：新增 `GET /approvals` 和 `POST /approvals/{id}/resolve` 端点，消除 standalone agent 的审批死锁

## Capabilities

### New Capabilities
- `standalone-agent-approval`: standalone agent (`fleetent agent run`) 暴露审批端点，支持 medium/high 风险工具在无 platform 场景下完成审批流程

### Modified Capabilities
- `tool-access-control`: `allowed_tools` 空列表的语义从"屏蔽全部"修正为"允许全部"，与文档描述一致
