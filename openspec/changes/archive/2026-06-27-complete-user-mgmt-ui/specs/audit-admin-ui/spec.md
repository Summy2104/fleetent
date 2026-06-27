## ADDED Requirements

### Requirement: 审计日志查看器

管理 SPA SHALL 提供审计日志查看页面,对接既有 `GET /admin/audit`。页面 SHALL 支持按 actor、action、target、时间范围检索,并以表格展示 who / when / resource / action 字段。检索条件变化时 SHALL 重新拉取并刷新结果。

#### Scenario: 按条件检索审计日志

- **WHEN** 管理员在审计页面设置 action 过滤(如 `rotate_key`)并提交检索
- **THEN** 调用 `GET /admin/audit` 携带该过滤条件,表格展示匹配条目(含 actor、时间、target、action)

#### Scenario: 无结果时给出明确空态

- **WHEN** 检索条件无任何匹配条目
- **THEN** 页面展示空态提示,而非空白或加载态卡死

### Requirement: 审计结果可导出

审计日志查看页面 SHALL 提供将当前过滤结果导出的入口(如 CSV),导出内容 SHALL 与当前检索条件一致。

#### Scenario: 导出当前过滤视图

- **WHEN** 管理员在已过滤的审计视图上点击导出
- **THEN** 导出文件包含且仅包含当前过滤条件下的审计条目
