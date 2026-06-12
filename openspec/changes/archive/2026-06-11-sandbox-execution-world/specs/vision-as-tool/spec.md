## MODIFIED Requirements

### Requirement: 入站图片存盘,主上下文仅带引用

入站图片 SHALL 写入 per-scope sandbox workspace 下的 `uploads/` 目录(容器内 `/workspace/uploads/`,= 宿主对应 workspace 子目录),与入站非图片文件的暂存目录一致(统一坐标系)。主对话上下文 MUST 仅携带该图片的 **workspace 相对引用**(如 `uploads/<name>.png`)而非 base64,MUST NOT 携带宿主绝对路径。`analyze_image` MUST 通过该引用经 workspace 解析(容器内 `/workspace/uploads/...`,或无-docker 降级时经宿主 workspace 围栏读同一物理文件)读取图片字节,而非要求 base64 在上下文中流转、也不再依赖宿主绝对路径回读;迁移 MUST 保持 `analyze_image` 既有契约——同一引用在迁移后仍能被回读、错误引用仍返回错误结果文本而不抛异常。

#### Scenario: 图片存盘并以 workspace 相对引用入上下文
- **WHEN** 一条含图片的入站消息被处理
- **THEN** 图片字节被写入 per-scope workspace 的 `uploads/` 子目录,主上下文携带其 workspace 相对引用(`uploads/<name>.png`),不携带 base64、不携带宿主绝对路径

#### Scenario: analyze_image 经 workspace 解析回读
- **WHEN** `analyze_image` 收到一个有效的 workspace 相对图片引用
- **THEN** 它经 workspace 解析读到该图片字节(容器内 `/workspace/uploads/...` 或宿主 workspace 围栏同址),完成理解,不依赖宿主绝对路径

#### Scenario: 迁移后无效引用仍返回错误文本
- **WHEN** `analyze_image` 收到一个 workspace 内不存在的图片引用
- **THEN** 返回说明引用无效的错误结果文本,不抛异常、不中断循环(既有契约不破坏)
