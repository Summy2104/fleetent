## ADDED Requirements

### Requirement: NormalizedMessage 支持出站图片上传（upload_func）

`NormalizedMessage` SHALL 在入站图片（attachments）支持的基础上，新增出站方向：`upload_func` 可选回调用于上传 agent 生成的图片，覆盖"入站下载 → attachments"和"出站生成 → upload"两个方向的图片流转。

#### Scenario: 入站图片不受影响
- **WHEN** 适配器设置了 `upload_func` 的同时，用户发送含图片的消息
- **THEN** `attachments` 行为与改动前完全一致，`upload_func` 只在本轮有生成图片时被调用
