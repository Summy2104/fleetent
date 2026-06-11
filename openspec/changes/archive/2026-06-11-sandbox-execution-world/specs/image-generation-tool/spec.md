## MODIFIED Requirements

### Requirement: 生成图存盘并返回短引用

生成的图片 SHALL 保存到 per-scope sandbox workspace 下的 `generated/` 目录(容器内 `/workspace/generated/`,= 宿主对应 workspace 子目录),工具返回值 MUST 为指向该图片的 **workspace 相对引用**(如 `generated/<name>.png`),MUST NOT 返回宿主绝对路径,MUST NOT 将图片 base64 内联进工具结果。该相对引用 MUST 满足 `sandbox-workspace-root` 的相对路径不变式:容器模式与无-docker 降级模式按同一相对引用解析到同一物理文件。生成图的 base64 数据 MUST NOT 进入对话上下文或运行日志(trace)。

#### Scenario: 返回 workspace 相对引用而非 base64
- **WHEN** `generate_image` 成功生成一张图片
- **THEN** 工具结果为指向已存盘图片的 workspace 相对引用(`generated/<name>.png`),不含 base64、不含宿主绝对路径

#### Scenario: 生成图落在 workspace/generated
- **WHEN** `generate_image` 成功生成一张图片
- **THEN** 图片字节被写入 per-scope workspace 的 `generated/` 子目录(容器内 `/workspace/generated/`),可经文件工具按 `generated/<name>.png` 读回

#### Scenario: trace 不含生成图 base64
- **WHEN** 一次含 `generate_image` 调用的运行写入 trace
- **THEN** trace 中不含生成图的完整 base64 串
