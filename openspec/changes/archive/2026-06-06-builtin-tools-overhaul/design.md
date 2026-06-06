## Context

fleetent 内置工具层当前 12 个工具，注册基础设施（`registry.py` + `result_truncation.py`）已投入生产但存在三个结构性限制：`_build_schema()` 仅支持 4 种原始类型（无法声明 `list[str]`、`Optional`、`Literal`、参数级描述）；截断策略为盲截断（head+tail，数据丢失，无后续操作提示）；所有工具无论是否可用均暴露给 LLM（`run_code` 无 Docker 时调用报错）。这三个限制阻碍了新工具扩展。

本 change 在修复基础设施的同时，新增文件操作工具链（edit/search）、Shell 执行、Web 访问和交互工具，完成企业 agent 核心能力覆盖。

## Goals / Non-Goals

**Goals:**
- 修复 `_build_schema()` 类型系统，支持 `list[T]`、`Optional[T]`、`Literal`、`Annotated`
- 升级截断策略：超限写溢出文件，返回 preview + 路径 + 分段读取提示
- 为 `@tool` 加 `availability` 声明，`get_schemas()` 过滤不可用工具
- 完整文件操作工具链：`read_file`（分页/目录/二进制）、`edit_file`（6 层 fallback）、`search_content`（grep）、`search_files`（glob）
- `bash_exec`：宿主机 Shell，强制 description，全量 permission_gate
- `web_fetch` / `web_search`（SearXNG 自托管）
- `clarify`：user_input_gate + IM 平台差异化渲染；`todo`：session 便签

**Non-Goals:**
- LSP 集成（opencode 实验性，暂不引入）
- Plan 模式（只读 agent）
- edit_file Levenshtein 模糊匹配（v1 不做，有误替换风险，待生产数据验证后评估）
- bash_exec Tree-sitter 命令 AST 解析（v1 用 description 字段 + permission_gate 审批替代）
- 浏览器自动化（Playwright，不在本 change 范围）

## Decisions

### D1：`_build_schema()` 用 `typing` 模块内省，不引入 pydantic

**选择**：`typing.get_origin()` / `typing.get_args()` 递归解析，支持 `list[T]`、`Optional[T]`、`Literal[...]`、`Annotated[T, str]`，约 60 行代码。

**排除**：pydantic schema 生成——功能强大，但 pydantic-settings 已在 config 层使用，若工具层也依赖 pydantic Model，会引入不必要的抽象层并影响 `@tool` 装饰器的轻量感；schema 字段需要 `Field()` 而非 `Annotated` 标注，改动面大。

**实现**：提取到独立 `schema_builder.py` 模块，`_build_schema()` 委托给它；`_OUT_OF_BAND_PARAMS` 过滤逻辑不变。

### D2：`edit_file` 实现 6 层 fallback，不含 Levenshtein

**选择**：
1. `ExactReplacer`：完全精确匹配
2. `LineTrimmedReplacer`：每行 `strip()` 后比较
3. `WhitespaceNormalizedReplacer`：连续空白视为等价
4. `LineEndingNormalizedReplacer`：`\r\n` → `\n`
5. `IndentationFlexibleReplacer`：移除公共缩进后比较
6. `ContextAwareReplacer`：首行+尾行精确锚定，中间行 `strip()` 比较

**排除 Levenshtein**（opencode 第 8 层）：相似但不同的代码块（同名函数不同参数、同结构不同逻辑）可能被错误替换，v1 不引入；生产失败模式数据积累后再评估。

**层间关系**：每层独立实现，按序尝试，第一个命中即返回，失败时返回「尝试了 N 层均失败」的诊断。

### D3：`bash_exec` 全量 permission_gate，`description` 字段必填

**选择**：`risk_level="high"` 触发 permission_gate 全量审批；`description` 参数为必填 string（5-10 词命令意图），不进 LLM schema 之外的任何隐式推断。

**agent.yaml 白名单扩展**（延后）：本 change 不实现参数级 `Bash(git:*)` 匹配，但 `bash_exec` 的 `description` 字段已提供人类可读的审批上下文，可作为 v1 白名单依据；参数级正则白名单作为后续 `tool-call-guardrails` 扩展。

**与 `run_code` 的双轨制**：
- `run_code`：Docker 沙箱，Python only，无网络，无宿主文件访问 → 不可信代码执行
- `bash_exec`：宿主机直接执行，任意命令，有 permission_gate → 运维/DevOps 操作

### D4：`clarify` 新建 `user_input_gate`，不复用 `permission_gate`

**选择**：在 `governance/user_input_gate.py` 新建独立模块，session 级 `asyncio.Event` + 答案存储，语义为「等待用户输入」而非「等待权限审批」。

**排除复用 permission_gate**：`permission_gate` 的语义是「高风险操作的人工审批」，其 approval/rejection 路径、超时逻辑、日志字段均面向安全场景；`clarify` 是流程决策，混用会污染 permission_gate 的安全审计语义，也难以支持 choices 的 IM 差异化渲染。

**IM 渲染策略**（分层实现）：
- `normalizer.py`：识别 `clarify` 工具调用，生成 `ClarifyRequest` 事件
- `slack.py`：Block Kit Section + Actions（Button 列表）
- `telegram.py`：`InlineKeyboardMarkup`
- 其他 / fallback：纯文字 choices 编号列表
- 用户点击/回复 → `user_input_gate.answer(session_id, answer)` → `event.set()`

**超时**：默认 300 秒（5 分钟），可通过 `ToolContext.features["clarify_timeout"]` 覆盖；超时返回字符串 `"timeout: 用户未在 {N} 秒内回答"`，agent 可继续处理。

### D5：`web_search` 后端用 SearXNG，availability 门控

**选择**：`SEARXNG_URL` 环境变量配置 SearXNG 实例地址；`availability=lambda: bool(os.getenv("SEARXNG_URL"))` 确保未配置时工具不出现在 LLM schema 中（不报错，不存在）。

**排除商业搜索 API**（Brave/Google/Exa）：违反企业数据主权原则（查询内容出内网）；SearXNG 有官方 Docker 镜像，企业可自托管，是唯一合规方案。

### D6：溢出文件存储在 `data_dir() / "tool_spillover"`

**选择**：与 fleetent 数据目录规范一致（`paths.data_dir()` 统一管理），文件名使用 `uuid4().hex`（不用 ULID，无需引入新依赖），7 天自动清理通过现有 `cron_scheduler` 注册每日任务。

**排除 `/tmp`**：OS 重启清理不可控，路径在不同部署中行为不一致；`data_dir` 在 FLEETENT_HOME 隔离下对测试友好。

### D7：`availability` 为 `Callable[[], bool]`，不用结构化 dict

**选择**：`@tool(availability=lambda: shutil.which("rg") is not None)`，轻量、pythonic、无需引入新数据结构；缺点是不能自动生成「不可用原因」提示，但 agent 看不到不可用工具，不需要原因。

**排除 openclaw 的结构化信号**（`{kind: "env", var: "SEARXNG_URL"}`）：增加了 DSL 复杂度，对 Python 工具注册场景不自然；lambda 已足够表达所有需要的条件（env var、二进制存在、config 字段）。

### D8：新工具按领域拆分独立文件

`builtin_tools.py` 保留现有 12 个工具，新工具写入各自领域文件，通过 `tools/__init__.py` 统一 import：

```
tools/
  file_tools.py         ← read_file(升级) + edit_file + search_content + search_files
  shell_tool.py         ← bash_exec
  web_tools.py          ← web_fetch + web_search
  interaction_tools.py  ← clarify + todo
  schema_builder.py     ← _build_schema 新实现
```

`builtin_tools.py` 中的 `read_file` / `write_file` 迁移至 `file_tools.py`（`builtin_tools.py` 留 re-export shim 避免破坏性变更）。

## Risks / Trade-offs

**[edit_file Layer 6 ContextAwareReplacer 误替换风险]** → 仅当首行+尾行完全精确匹配时才激活；若文件中存在多处满足条件的块，返回错误要求用户提供更精确的 old_string，不静默替换

**[bash_exec 全量审批阻断 cron 场景]** → cron 触发的 agent 遇到 bash_exec 会挂起等待，与 permission_gate 现有行为一致（cron agent 的高危操作本应挂起等待审批）；后续 `tool-call-guardrails` 扩展可加白名单机制

**[clarify 在 webhook/API 场景无法渲染 choices]** → webhook/API 触发的会话没有 IM 渲染层，clarify 将降级为纯文字问题；超时后 agent 收到 timeout 结果，需自行决策；这是可接受的降级

**[SearXNG 搜索质量依赖实例配置]** → 搜索质量取决于企业侧 SearXNG 配置的搜索引擎（Google/Bing 需 API key）；fleetent 只做 HTTP 调用，不控制搜索质量；文档说明配置要求

**[ripgrep 外部二进制依赖]** → 通过 availability fallback 处理：有 rg 用 rg（快），无 rg 用 Python re 回退（慢但可用）；Docker 基础镜像已含 rg（Dockerfile 确认）

**[溢出文件磁盘占用]** → 7 天清理 + 单文件上限 50KB，极端场景（大量并发工具调用）下磁盘压力有限；data_dir 通常在有容量控制的挂载点

## Migration Plan

1. Sprint 1（基础设施）独立部署：`schema_builder.py` 完成后现有 `@tool` 工具无感，`result_truncation` 阈值从 40KB → 50KB 是向上兼容，`availability` 新参数默认 None（全暴露）
2. Sprint 2-4 各 sprint 为独立可测试、可部署单元，不存在跨 sprint 的硬依赖
3. `read_file` 升级时原有 `path` 参数不变，新增 `offset=1` / `limit=200` 均有默认值，向后兼容
4. 回滚：任意 sprint 可独立回滚，工具注册是副作用模式，删除 import 即可注销

## Open Questions

- `bash_exec` 是否需要禁止命令黑名单（`rm -rf /`、`dd` 等）？建议 v1 通过 permission_gate 审批代替黑名单，黑名单维护成本高且易绕过
- `web_fetch` 是否需要支持 HTTP 代理配置（企业内网访问外网）？建议通过标准 `HTTP_PROXY` / `HTTPS_PROXY` 环境变量，httpx 原生支持
- `clarify` 超时时间 300 秒是否合理？可通过 `features["clarify_timeout"]` 覆盖，平台级默认值后续按实际使用调整
