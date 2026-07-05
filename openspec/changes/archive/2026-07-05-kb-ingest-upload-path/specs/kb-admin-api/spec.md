# kb-admin-api — Delta

## ADDED Requirements

### Requirement: Document upload proxy

平台 SHALL 提供 `POST /admin/kb/{kb_id}/documents`(multipart)供管理员上传单个文档:admin-only(viewer 403),经 `KBServeClient` 以 multipart 透传到租户 kb-serve 的上传端点,响应透传 job id 与 serve 端错误码(404/413 等)。成功受理 SHALL 写审计条目(`doc_upload`,含 kb_id 与原始文件名)。平台侧 SHALL NOT 自行解析 / 切块 / 写库——上传的一切处理归 KB 服务侧。

#### Scenario: 管理员上传文档
- **WHEN** 管理员对 kb_id "support" 上传 `handbook.pdf`
- **THEN** 请求被透传到该租户 kb-serve,响应含 job id,审计写入 `doc_upload`;文档经 kb-worker 消费后出现在 `GET /admin/kb/support/documents`

#### Scenario: viewer 不能上传
- **WHEN** viewer 角色调用上传端点
- **THEN** 返回 403,不产生 serve 端调用与审计

#### Scenario: serve 端错误透传
- **WHEN** kb-serve 返回 413(超限)或 404(KB 不存在)
- **THEN** 平台端点向调用方透传同一错误码,不写 `doc_upload` 审计
