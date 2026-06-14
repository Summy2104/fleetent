# provider-admin-ui Delta

## REMOVED Requirements

### Requirement: Task-type routing
**Reason**: `model_routes` 表与 `/admin/providers/routes` 端点 descope——该 UI 调 `PUT /admin/providers/routes/{task_type}` 编辑的是 runtime 从不读的表。模型路由真相源为 `agent.yaml` `model_overrides` + `ROUTES_PATH` YAML（非控制台 DB 表）。
