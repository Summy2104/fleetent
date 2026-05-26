# Agent Runtime 子功能索引

> 全部 63 个子功能扁平索引表，配简短功能描述
> 详见 [agent-runtime-capabilities.md](./agent-runtime-capabilities.md)（完整契约）与 [agent-runtime-acceptance-criteria.md](./agent-runtime-acceptance-criteria.md)（验收场景）

| 编号 | 模块 | 子功能 | 简短描述 |
|:----:|:----|:------|:--------|
| 1.1  | 核心循环 | 主循环执行 | while 调 LLM + 处理 tool_use，自然/强制终止 |
| 1.2  | 核心循环 | 三种调用入口 | run / run_stream / run_sync 共享同一循环核 |
| 1.3  | 核心循环 | 终止条件管理 | 闭集枚举原因码（自然/配额/失败/人工/循环） |
| 1.4  | 核心循环 | 模型 fallback 链 | 主模型失败时按顺序切换 fallback，记录实际 model |
| 1.5  | 核心循环 | 工具调用调度 | 按工具属性分级（PARALLEL_SAFE/PATH_SCOPED/NEVER） |
| 1.6  | 核心循环 | 中断与取消传播 | cancel 穿透到 LLM/tool/sandbox/MCP |
| 1.7  | 核心循环 | 循环检测 | 工具签名重复 N 次警告，再重复硬停 |
| 1.8  | 核心循环 | 迭代预算与 grace call | 三维预算耗尽时给一次 final-reply 机会 |
| 1.9  | 核心循环 | 错误分类与重试 | enum-driven，主循环只读恢复策略标志 |
| 1.10 | 核心循环 | 消息卫生与契约修复 | 角色交替、tool pair、JSON 合法性兜底 |
| 2.1  | 工具 | 工具注册 | 装饰器声明，import 时入 registry |
| 2.2  | 工具 | Schema 自动推导 | 从函数签名 + docstring 生成 JSON Schema |
| 2.3  | 工具 | 命名规范与命名空间 | 内置无前缀，MCP 双下划线 `server__tool` |
| 2.4  | 工具 | 描述规范 | 面向 LLM 的高质量描述（Anthropic 规范） |
| 2.5  | 工具 | Dispatch 与超时 | 强超时 + 异常隔离，失败也返回 tool_result |
| 2.6  | 工具 | 结果格式化与大小限制 | 头尾截断 + 单/全 session 双层 cap |
| 2.7  | 工具 | 风险分级与审批联动 | low 自动 / medium 提示 / high 必审批 |
| 2.8  | 工具 | 访问控制白名单 | agent allowed_tools fnmatch 匹配 |
| 2.9  | 工具 | 工具来源分层 | builtin / mcp / user / sub_agent 打标 |
| 2.10 | 工具 | 调用守卫 (guardrails) | 重复/连续失败/无进展检测，警告→硬停 |
| 2.11 | 工具 | 参数消毒与 secret 过滤 | JSON 修复 + 三层 env 过滤 |
| 3.1  | Skill | 扫描与发现 | 递归扫 SKILL.md，启动期一次 |
| 3.2  | Skill | Frontmatter 解析 | YAML 提取 name/description/platforms 等 |
| 3.3  | Skill | 平台/上下文过滤 | platforms 字段决定当前环境是否启用 |
| 3.4  | Skill | 渐进式披露 | L1 metadata / L2 全文 / L3 引用文件三层加载 |
| 3.5  | Skill | 多 skill 共存与冲突 | L1 全注入；L2 首次命中；命名冲突报警 |
| 3.6  | Skill | 热加载与重扫描 | 显式 reload，原子切换索引 |
| 3.7  | Skill | 信任与审计 | 检测 16 类 injection 模式，严重模式拒载 |
| 3.8  | Skill | 禁用机制 | config disabled 列表三层覆盖 |
| 4.1  | MCP | stdio transport | 子进程 stdin/stdout JSON-RPC |
| 4.2  | MCP | Streamable HTTP transport | POST + SSE，可恢复流 |
| 4.3  | MCP | Server 注册与配置 | config 声明，部分失败不阻断启动 |
| 4.4  | MCP | 工具命名空间化 | `{server}__{tool}` 双下划线避免冲突 |
| 4.5  | MCP | Session 管理 | Mcp-Session-Id header，过期自动重建 |
| 4.6  | MCP | OAuth / 认证 | token 自动刷新，失败标记不可用 |
| 4.7  | MCP | 健康检查与重连 | 周期 ping + 指数退避重连 |
| 4.8  | MCP | 失败降级 | 默认 degrade（屏蔽该 server 工具） |
| 4.9  | MCP | Sampling 沙箱化 (v1+) | server 请求 LLM 走独立 aux client + 限流 |
| 5.1  | 沙箱 | 可插拔隔离档位 | Docker / gVisor / Firecracker / SSH 可插 |
| 5.2  | 沙箱 | 资源限制 | CPU/Mem/Net/FS/进程 全维度上限 |
| 5.3  | 沙箱 | 环变过滤与 secret 防泄 | passthrough → 名字含 KEY → 安全前缀三层 |
| 5.4  | 沙箱 | 文件系统隔离 | workspace 边界 + symlink resolve 校验 |
| 5.5  | 沙箱 | 输出截断 | stdout 50KB / stderr 10KB 头尾保留 |
| 5.6  | 沙箱 | 执行超时与级联终止 | SIGTERM → SIGKILL，确保容器清理 |
| 5.7  | 沙箱 | 多语言支持 | Python 必备，Node/Bash 可选 |
| 5.8  | 沙箱 | 可观测性穿透 | stdout/stderr/exit_code/duration 入 trace |
| 5.9  | 沙箱 | Warm pool (v1+) | 池化预启动摊薄冷启动延迟 |
| 6.1  | 上下文压缩 | 触发条件（双阈值） | Tmax 触发 → 压至 Tretained，留 bandwidth |
| 6.2  | 上下文压缩 | 头-中-尾分层 | 头强保 + 尾按 token 预算 + 中段摘要 |
| 6.3  | 上下文压缩 | 持久化增量摘要 | 仅摘新中段 merge 进 persistent summary |
| 6.4  | 上下文压缩 | Tool pair 完整性 | 切点避开 pair；孤立 use 补占位、孤立 result 移除 |
| 6.5  | 上下文压缩 | 工具结果预修剪 | 廉价替换老 tool_result + 图像占位 |
| 6.6  | 上下文压缩 | 摘要质量与失败处理 | aux LLM 结构化摘要，失败回退静态截断 |
| 6.7  | 上下文压缩 | 元数据与可追溯 | trigger/before_tokens/after/duration 入 trace |
| 6.8  | 上下文压缩 | 镜像/二进制处理 | 图像 content block 替换为文本占位符 |
| 6.9  | 上下文压缩 | 反抖动 | 连续 N 次无效压缩 → 关闭自动压缩 |
| 7.1  | 横切 | Trajectory / Trace | 所有事件 append-only JSONL，PII redact |
| 7.2  | 横切 | 审批门 | asyncio.Event 异步阻塞，超时默拒 |
| 7.3  | 横切 | 成本预算 | run/session/user/agent/global 多层级 |
| 7.4  | 横切 | 错误分类（统一 codec） | 12+ 枚举，每项携带恢复策略标志 |
| 7.5  | 横切 | 取消与超时传播 | cancel token 单向流，cooperative + 硬 deadline |
| 7.6  | 横切 | 沙箱可观测性穿透 | 隔离环境的执行细节进 trace |
| 7.7  | 横切 | 插件钩子 (v1+) | 关键节点 hook，失败默认 pass |

---

## 子功能分布

| 模块 | 子功能数 | v1 必做 | v1+ 可选 |
|------|:----:|:----:|:----:|
| 1 核心循环 | 10 | 10 | 0 |
| 2 工具 | 11 | 11 | 0 |
| 3 Skill | 8 | 8 | 0 |
| 4 MCP | 9 | 8 | 1（4.9 sampling） |
| 5 沙箱 | 9 | 8 | 1（5.9 warm pool） |
| 6 上下文压缩 | 9 | 9 | 0 |
| 7 横切关注点 | 7 | 6 | 1（7.7 hooks） |
| **总计** | **63** | **60** | **3** |

## 标记说明

- **v1 必做** = 进入第一版交付范围
- **v1+ 可选** = 推迟到后续版本，但接口/数据结构预留
- 列表中标注「(v1+)」者属第二类
