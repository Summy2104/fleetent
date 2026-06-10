## 1. 文件附件契约（FileAttachment + picker）

- [x] 1.1 Write failing tests for FileAttachment contract: normalizer 定义 `FileAttachment(data, mime, filename, note)`；`_file_attachments` 挑出文件项；`_image_attachments` 对混入文件项的 attachments 行为不变（只挑图片二元组）
- [x] 1.2 Implement FileAttachment dataclass 与 `_file_attachments` picker to pass tests

## 2. 网关下载（slack.py 单函数扩展）

- [x] 2.1 Write failing tests for `_download_attachments`: 非图片文件下载为 `FileAttachment(data, mime, filename)`；超过 20 MB 上限不下载、产出 `data=None` + 超限 note；下载失败记 warning、产出 `data=None` + 失败 note、不抛异常；图片仍产出 `(bytes, mime)` 二元组且行为与现状一致（mock httpx）
- [x] 2.2 Implement `_download_attachments`（改造 `_download_image_attachments`）to pass tests
- [x] 2.3 Write failing tests for 三条接收路径（assistant 面板 / `app_mention` / DM `message`）：含 xlsx 事件经真实 handler 路由后 `NormalizedMessage.attachments` 含文件项（复用 test_slack_per_agent / test_slack_session harness）
- [x] 2.4 Update 三条路径调用点 to pass tests

## 3. workspace 落盘与文件名安全化

- [x] 3.1 Write failing tests for 落盘：文件写入 session workspace 的 `uploads/` 子目录（mock sandbox manager 的 `workspace_host_path` 指向 tmp_path）；文件名安全化（`../../etc/passwd` → basename 化、剥离危险字符、保留扩展名、空名回退）；同名冲突加唯一前缀不覆盖；定位 workspace 不触发 docker 连接
- [x] 3.2 Implement workspace 写盘与安全化 to pass tests

## 4. 消息注入（_build_user_content）

- [x] 4.1 Write failing tests for 注入：成功文件 → 用户消息含原文本 + 原始文件名 + workspace 相对路径 + 工具提示；`data=None` → 含「未能接收」与 note 的占位文本；无文件消息行为与改动前一致；图片 + 文件混合各走各通道（图片仍 vision 抽取，文件不触发 vision、字节不进上下文）
- [x] 4.2 Implement `_build_user_content` 文件分支 to pass tests

## 5. 收尾验证

- [x] 5.1 跑受影响层 `uv run pytest tests/unit -q`，确认无新增失败
- [x] 5.2 `make test-pr` 全绿 + `uv run pytest tests/integration -q` 对照 main 基线无新增失败
- [x] 5.3 本地端到端复现验证：用 AAA-8053 复现脚本（驱动真实 handler 的 xlsx 事件）确认三条路径下 agent 收到的消息含文件引用且文件已落盘可读
