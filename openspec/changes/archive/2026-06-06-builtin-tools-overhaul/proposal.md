## Why

fleetent 当前内置工具仅 12 个，文件操作原始（无分页、无精准编辑、无搜索），缺少 Shell 执行、Web 访问和结构化用户交互，与业界同类产品（claude-code、opencode、hermes、openclaw）对比存在系统性能力缺口，导致 agent 在代码助手、运维自动化、信息检索等核心企业场景中无法有效完成任务。工具注册基础设施（schema 类型系统、输出截断、可用性声明）同样落后，已成为新工具扩展的结构性瓶颈。

## What Changes

**基础设施层**
- `_build_schema()` 升级：支持 `list[T]`、`Optional[T]`、`Literal[...]`、`Annotated[T, desc]` 类型注解，解锁参数级描述和枚举约束
- `@tool` 装饰器新增 `availability` 参数：声明工具的运行时可用性条件（环境变量、二进制依赖等）；`get_schemas()` 过滤不可用工具，agent 看到的始终是当前可用集合
- `result_truncation` 升级：超 50KB 时写入溢出文件（7 天自动清理），返回前 100 行 + 文件路径 + 分段读取提示，替代盲截断

**文件操作工具链**
- `read_file` 升级：新增 `offset`（1-indexed 行号）、`limit` 参数；支持目录列举（树形结构含 size/mtime）；内建二进制文件检测（magic bytes + 非打印字符比例）
- `edit_file`（新增）：`old_string → new_string` 精准替换，6 层 fallback 匹配（精确 / 行 trim / 空白归一化 / 换行归一化 / 缩进归一化 / 上下文锚点），`replace_all` 可选，误替换安全检查
- `search_content`（新增）：正则内容搜索，ripgrep 后端（Python re 回退），返回 `文件:行号:匹配行`
- `search_files`（新增）：glob 文件名/路径搜索，ripgrep 后端，按 mtime 降序，结果上限 100

**执行工具**
- `bash_exec`（新增，risk_level=high）：宿主机直接 Shell 执行，区别于 Docker 沙箱的 `run_code`；`description` 必填（5-10 词命令意图，用于权限审查展示）；50KB 输出上限 + 溢出文件；支持 CancelToken；全量 permission_gate 审批

**网络工具**
- `web_fetch`（新增）：httpx 异步 HTTP 获取，HTML→Markdown 转换（html2text），5MB 响应上限，availability 无前置要求
- `web_search`（新增）：SearXNG 自托管搜索后端，`SEARXNG_URL` 环境变量配置，availability 门控（未配置时不暴露给 LLM）

**交互工具**
- `clarify`（新增）：agent 主动向用户提问，`question` + 可选 `choices: list[str]`；新建 `user_input_gate`（asyncio.Event + 答案存储），session 级别管理；IM 渲染层按平台差异化（Slack Block Kit 按钮 / Telegram InlineKeyboard / 文字 fallback）；超时返回 timeout 结果
- `todo`（新增）：session 级别任务追踪便签（内存，session 结束自动清除），action=set/get/clear，用于长任务进度管理

## Capabilities

### New Capabilities
- `builtin-file-tools`：read_file 升级 + edit_file + search_content + search_files 的完整文件操作工具链
- `builtin-shell-tool`：bash_exec 宿主机 Shell 执行工具及其双轨制定位（sandbox vs direct）
- `builtin-web-tools`：web_fetch + web_search 网络访问工具，web_search 通过 SearXNG 自托管
- `builtin-interaction-tools`：clarify（结构化用户提问 + user_input_gate）和 todo（session 便签）
- `tool-schema-builder`：`_build_schema` 完整类型系统支持
- `tool-availability`：`@tool(availability=...)` 声明 + `get_schemas()` 过滤机制

### Modified Capabilities
- `tool-result-truncation`：截断策略从盲截断升级为溢出文件 + 前 100 行 preview + 分段读取提示

## Impact

- **核心改动文件**：`src/fleetent/tools/builtin_tools.py`、`src/fleetent/tools/registry.py`、`src/fleetent/tools/result_truncation.py`
- **新增文件**：`src/fleetent/tools/file_tools.py`（文件工具实现）、`src/fleetent/tools/web_tools.py`（网络工具）、`src/fleetent/tools/shell_tool.py`（bash_exec）、`src/fleetent/tools/interaction_tools.py`（clarify/todo）、`src/fleetent/tools/schema_builder.py`（类型系统）
- **IM 网关改动**：`im_gateway/slack.py`、`im_gateway/telegram.py`、`im_gateway/normalizer.py`——新增 clarify choices 渲染和用户回答路由
- **新增依赖**：`html2text`（HTML→Markdown）；`ripgrep` 二进制（外部，回退 Python re）
- **破坏性变更**：无（read_file 新参数均有默认值；tool_result_truncation 阈值从 40KB 升至 50KB，影响极小）
- **permission_gate**：bash_exec 强制集成，clarify 新建独立 user_input_gate 通道（不复用 permission_gate）
