# task-type-routing-console Delta

## REMOVED Requirements

### Requirement: Visual task_type routing order edit
**Reason**: `model_routes` 表 descope——该控制台编辑/保存的 `model_routes` 表 runtime 从不消费（模型路由真相源是 per-agent `agent.yaml` `model_overrides` + 全局 `ROUTES_PATH` YAML）。整个控制台连同 `/admin/providers/routes` 端点移除。

### Requirement: Unknown task_type fallback is shown
**Reason**: 控制台整体移除（同上）。

### Requirement: Fallback chain preview
**Reason**: 控制台整体移除；预览读取的是 runtime 不消费的 `model_routes` 表。

### Requirement: Health probe status visibility
**Reason**: 路由控制台移除。provider 健康数据本身仍由 `provider-health-probe`（`GET /admin/providers/health`，保留）提供；将来如需独立的路由健康视图可单独加回。

### Requirement: Routing edits are role-gated
**Reason**: 无路由编辑端点后此角色门控失去对象。
