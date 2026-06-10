## Context

Slack 入站消息的文件附件只有一条处理通道：`slack.py::_download_image_attachments`，仅下载 `image/*` mime，其余文件静默跳过（AAA-8053 根因，三条接收路径 assistant 面板 / 频道 @mention / DM 共用此函数）。图片的既有范式是「网关下载字节 → normalizer 落盘 `data/uploads/` → vision 一次性分析 → 以文本引用注入消息，base64 不进主循环」。

对非图片文件照搬 uploads 落点不可行：agent 消费文档靠 `read_file` / `run_code`，而这两者被**锁定在 per-session sandbox workspace**（容器内 `/workspace` bind-mount，host-degrade 模式围栏到同一 host 目录，见 `file_tools.py` 与 `sandbox/manager.py::workspace_host_path`）；`data/uploads/` 只有 host 侧 `analyze_image` 可见。

## Goals / Non-Goals

**Goals:**

- Slack 上传的非图片文件能被 agent 感知并读取（修复 AAA-8053）
- 文件落点对 agent 现有工具（`read_file` / `run_code`）开箱可见，容器与 host-degrade 两种模式都能解析注入的路径
- 下载失败 / 超限不静默：agent 与用户能从消息中知道有文件但未能接收
- 图片通道行为零变化（attachments 图片二元组契约、vision 抽取判据不动）

**Non-Goals:**

- Telegram 文档附件接入（normalizer 侧通道平台无关，适配器接入留后续 change）
- 文档的一次性自动摘要 / 解析（vision 的等价物）——由 agent 按需用工具处理
- 新增专用文档解析工具或 sandbox 镜像预装解析库
- 文件持久化 / KB 摄取——文件生命周期跟随 session workspace

## Decisions

### D1：文件落点 = session sandbox workspace 的 `uploads/` 子目录（弃用 data/uploads/）

`read_file` 与 `run_code` 的可见根都是 workspace；落 `data/uploads/` 则 agent 拿到路径也读不到（围栏外）。normalizer 经 sandbox manager 的 `workspace_host_path(scope, session_id, agent_name)` 定位 host 目录写入；注入消息的是 **workspace 相对路径**（如 `uploads/笔记列表明细表.xlsx`），容器内（cwd=/workspace）与 host-degrade（围栏根=同一目录）均可解析。
*备选*：落 `data/uploads/` + 新增 `read_upload` 类工具——多造工具、打破 workspace 围栏一致性，弃。

### D2：attachments 文件项用独立 dataclass，与图片二元组共存

新增 `FileAttachment(data: bytes | None, mime: str, filename: str, note: str = "")`（定义在 normalizer，适配器构造）。`data=None` 表示下载失败/超限，`note` 说明原因。图片保持 `(bytes, mime)` 二元组——`_image_attachments` 现有 isinstance/len 判据天然忽略非二元组项，零破坏；新增 `_file_attachments` picker 挑出 `FileAttachment`。
*备选*：三元组 tuple——失败语义（None + 原因）表达不了，魔法元组可读性差，弃。

### D3：网关单函数扩展，三路径一处修复

`_download_image_attachments` 改造为 `_download_attachments`：`image/*` 走原逻辑产出二元组；其余 mime 下载为 `FileAttachment`，超过大小上限（常量 `_MAX_FILE_BYTES = 20 MB`）不下载、产出 `data=None` 的占位项（note 注明超限），下载失败同样降级为占位项 + warning，不抛异常。三条接收路径调用点各改一行。
*备选*：保留原函数另加新函数——两次遍历 `files`、两处调用点改动 ×3 路径，无收益，弃。

### D4：消息注入格式与图片对齐，不做自动分析

`_build_user_content` 对每个文件项追加一段：成功 → `[文件 {原始文件名} 已保存到 {workspace 相对路径}，可用 read_file 或 run_code 读取]`；失败/超限 → `[文件 {原始文件名} 未能接收：{note}]`。文档不做 vision 式一次性分析：xlsx/pdf 的「摘要」依赖任务意图，预分析既贵又常答非所问，agent 按需解析更准。

### D5：文件名安全化

写盘前对原始文件名做 basename 化、剥离路径分隔符与控制字符、保留扩展名；空名回退 `file`。同名冲突加 8 位 uuid 前缀。注入文本中展示原始文件名（用户语境），路径用安全化后的实名。

## Risks / Trade-offs

- [sandbox 容器无网络、镜像未必有 pandas/openpyxl，xlsx 解析可能失败] → xlsx 本质是 zip+xml，Python 标准库（zipfile + xml）即可解析，agent 可自行降级；镜像预装解析库属 sandbox 镜像演进，单列后续 change
- [run_code 容器 256 MB 内存，超大文件解析 OOM] → `_MAX_FILE_BYTES = 20 MB` 上限在网关侧挡住，超限有占位说明
- [normalizer（im_gateway）新增对 sandbox manager 的依赖] → 两者同属 agent 运行时，方向合法；manager 的 `workspace_host_path` 是纯目录解析/创建，不触发 docker 连接，host 无 docker 也可用（apply 时以测试验证）
- [恶意文件名路径穿越] → D5 安全化 + 写入仅限 workspace/uploads 子目录；文件本体只落入 sandbox 围栏内，不被宿主执行
- [文件生命周期跟随 workspace 清理（sweep/release）] → 接受：入站文件是会话级素材，与 session 同生命周期符合预期

## Migration Plan

无 schema / 配置 / 依赖变更。行为向后兼容：无文件消息路径完全不变；纯图片消息行为不变。回滚 = revert 代码。

## Open Questions

无阻塞项。
