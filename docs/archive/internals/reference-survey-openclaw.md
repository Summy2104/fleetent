# openclaw 调研笔记

> 项目类型：TypeScript + Node.js，一个多渠道 Agent 平台（macOS/iOS 客户端 + Gateway + 多消息渠道），支持跨 LLM provider 的自主 Agent 执行、工具调用、MCP 集成和会话管理。

## 1. 核心循环（Agent Loop）

### 1.1 它做了什么

- **主循环入口**：`runEmbeddedPiAgent` (pi-embedded-runner/run.ts:260+) 实现核心 while 循环，支持重试、failover、context overflow 处理。
- **Attempt-based 架构**：每个 agent run 被分解为多个 attempt，每个 attempt 包含 model invocation、tool dispatch、result collection（run/backend.js）。
- **多层重试**：支持模型 idle timeout 重试、auth 失败轮换、rate-limit fallback、context overflow 自动 compaction 后重试。
- **流式 vs 非流式**：采用基于事件流的 pi-agent-core 接口，订阅 model delta/tool start/end 事件，实时转换为 assistant/tool/lifecycle 流事件。
- **终止条件**：阶段化终止判断——model 返回 stop_reason=end_turn/tool_use，所有 tool 完成，或模型无新内容 → lifecycle end/error。
- **错误处理与 fallback**：
  - classifyFailoverReason (pi-embedded-helpers.js) 分类 auth/billing/rate-limit/context-overflow/model-error。
  - resolveRunFailoverDecision (run/failover-policy.js) 根据 profile 轮换策略、overload backoff (resolveOverloadFailoverBackoffMs) 决定是否重试。
  - 模型无新内容→empty response retry；auth 失败→auth profile cooldown + rotation；context overflow→压缩 + 重试。
- **并发与取消**：
  - per-session queue lane + optional global lane (resolveSessionLane/resolveGlobalLane)。
  - 由 command-queue (process/command-queue.js) 管理，支持 priority、timeout 控制。
  - AbortSignal 传播支持、idle timeout breaker (run/idle-timeout-breaker.js)。

### 1.2 关键设计点

- **State machines over callbacks**：attempt 结果被规范化为 normalized attempt object，包含 assistantTexts/toolMetas/messagesSnapshot，支持幂等重试和 compaction 边界判断。
- **Auth profile as first-class concept**：多 profile 支持，失败时自动轮换，cooldown 避免快速重试（markAuthProfileFailure/resolveAuthProfileEligibility）。
- **Context-aware failover**：failover decision logger (run/failover-observation.js) 记录决策过程，用于诊断和 telemetry。
- **Cleanup timeout machinery**：run-cleanup-timeout.ts 确保即使在超时/abort 情况下仍执行有限的清理步骤（如 session flush）。

### 1.3 关键文件清单

| 文件路径 | 用途 |
|---------|------|
| src/agents/pi-embedded-runner/run.ts | 主循环主体，attempt 协调、failover 决策 |
| src/agents/pi-embedded-runner/run/backend.js | 单次 attempt 执行，model invoke/tool dispatch |
| src/agents/pi-embedded-runner/run/failover-policy.ts | Failover 决策逻辑和 profile 轮换策略 |
| src/agents/pi-embedded-runner/run/idle-timeout-breaker.ts | Idle timeout 检测和 abort 机制 |
| src/agents/pi-embedded-runner/run/incomplete-turn.js | 空回复、单纯推理情况下的重试指令生成 |
| src/agents/pi-embedded-helpers.ts | Failover 原因分类、错误信号提取 |
| src/process/command-queue.js | 队列管理、per-session lane、priority/timeout |
| src/agents/pi-embedded-runner/compact.ts | Overflow compaction 入口 |

---

## 2. 工具（Tools）

### 2.1 它做了什么

- **工具注册机制**：agent 启动时动态收集工具——内置工具（gateway-tool、message-tool、cron-tool 等）+ MCP 工具（pi-bundle-mcp-tools.js）+ LSP 工具。
- **Schema 定义**：使用 TypeBox 定义工具 schema（Type/Type.Object/Type.String 等），运行时转换为 JSON Schema，传给模型。
- **Dispatch/执行**：
  - pi-agent-core 收集 model 的 tool_use block。
  - runEmbeddedAttemptWithBackend 遍历 tool calls，对每个调用：结果 check 大小（tool-result-truncation.ts）→ sanitize（session-tool-result-guard-wrapper.js）→ persist。
  - 超时由运行时配置控制（agents.defaults.sandbox.timeoutSeconds）。
- **访问控制**：
  - effective-tool-policy.ts 根据 channel 配置和 runtime policy 决定工具可用性。
  - tool-name-allowlist.ts 检查工具名合法性。
  - before_tool_call hook（plugin hooks）可以 block 工具执行。
- **内置 vs 用户自定义**：
  - 内置：gateway/message/cron/image-generate/pdf/web-fetch/sessions-* 等核心工具。
  - 用户：skills 提供额外工具，通过 SKILL.md 发布到 plugin-skills 目录，被 agent 发现。
- **结果格式化**：
  - tool-result-context-guard.ts 限制单个工具结果大小。
  - tool-result-truncation.ts 在整个 session 维度 truncate 过大结果（session likely has oversized results check）。
  - 图像结果进行 media staging 到 sandbox workspace。

### 2.2 关键设计点

- **Lazy tool collection**：工具列表在 run 时从 manifest registry/MCP/LSP 动态解析，不预生成，支持热加载。
- **Tool pair integrity**：compaction 和 truncation 时必须保持 tool_use/toolResult 配对，不能在中间切割。
- **Size-aware dispatch**：在执行前估算结果大小，超过阈值则 truncate 指令或拒绝执行。
- **Plugin hook intercepts**：before_tool_call/tool_result_persist hooks 让插件观察和变换工具调用与结果。

### 2.3 关键文件清单

| 文件路径 | 用途 |
|---------|------|
| src/agents/tools/gateway-tool.ts | Agent 可用的 config/update/gateway 操作工具 |
| src/agents/tools/message-tool.ts | 消息发送、会话通讯工具 |
| src/agents/tools/sessions-*.ts | 会话列表、管理、生成工具 |
| src/agents/tools/web-fetch.ts | Web fetch with SSRF guard 和 provider fallback |
| src/agents/tools/pdf-tool.ts | PDF 解析和提取工具 |
| src/agents/tools/image-generate-tool.ts | 图像生成（多 provider） |
| src/agents/pi-bundle-mcp-tools.ts | MCP 工具动态绑定和运行时管理 |
| src/agents/effective-tool-policy.ts | 工具可用性决策（channel policy/runtime policy） |
| src/agents/tools/tool-result-context-guard.ts | 单工具结果大小限制 |
| src/agents/tools/tool-result-truncation.ts | 整 session 工具结果截断 |

---

## 3. Skill

### 3.1 它做了什么

- **扫描发现**：resolvePluginSkillDirs (plugin-skills.ts) 遍历 plugin manifest registry，收集声明 skills[] 的插件，按 activation state 过滤。
- **存储和链接**：publishPluginSkills 在 ~/.openclaw/plugin-skills/ 下创建符号链接，指向各插件的 skill 目录，每个 skill 目录必须包含 SKILL.md。
- **注入位置**：skills 通过两个渠道注入：
  - 环境变量：applySkillEnvOverrides (skills.ts) 设置 SKILL_* 环境变量。
  - 提示词：resolveSkillsPromptForRun 将 skill markdown 内容拼接到系统提示。
- **多 skill 冲突解决**：skill 名称碰撞检查（hasPublishableSkillFile 验证 SKILL.md），同名时报警告，最后加载的 skill 优先。
- **生命周期**：skills 在 session start 时一次性加载（loadSkillsSnapshot），不支持热加载，但配置改变时需要手动 reload。
- **权限和激活**：plugin skill 通过 plugin activation state 控制（resolveEffectivePluginActivationState），memory plugin 有单选限制（resolveMemorySlotDecision）。

### 3.2 关键设计点

- **Declaration-based discovery**：skill 声明在 plugin manifest 的 skills[] 字段，不需要代码扫描。
- **Symlink-based publishing**：使用符号链接避免复制，支持 in-place skill 更新（重新扫描后需要 reload）。
- **Env + prompt dual injection**：某些 skill 可能需要 CLI 环境（如 SSH 密钥），也需要 LLM 语言指导。

### 3.3 关键文件清单

| 文件路径 | 用途 |
|---------|------|
| src/agents/skills/plugin-skills.ts | Skill 发现、发布、symlink 管理 |
| src/agents/skills/refresh.ts | Skill 重新加载和 snapshot 管理 |
| src/agents/pi-embedded-runner/compact.ts:L112 | applySkillEnvOverrides 调用位置 |
| src/agents/skills/command-specs.ts | Skill 命令 spec 定义和导出 |
| skills/ | 项目内置 skill 目录（各个子目录含 SKILL.md） |

---

## 4. MCP

### 4.1 它做了什么

- **Transport**：采用 @modelcontextprotocol/sdk，支持 stdio (StdioServerTransport)、HTTP/SSE（通过自定义 transport）。
- **Server 注册**：registerChannelMcpTools (channel-tools.ts) 向 McpServer 注册 tools，setToolHandler 处理工具调用。
- **工具命名**：MCP 工具名称采用 vendor/tool_name 格式，传给模型时被规范化为 tool_name。
- **认证**：
  - Gateway MCP bridge 支持 shared secret auth（token/password）。
  - Claude channel mode（auto/text-only）控制是否暴露 text/resource 等高阶能力。
  - ClaudePermissionRequestSchema 用于权限 UI 交互。
- **健康检查**：getChannelMcpCapabilities 报告 mcp 服务能力，支持定期 health endpoint。
- **降级**：pi-bundle-mcp-tools.js 包装 MCP runtime，失败时会回退到内置工具或静默失败。

### 4.2 关键设计点

- **Bridge pattern**：OpenClawChannelBridge 解耦 gateway/mcp protocol，支持多渠道（WhatsApp/Telegram/Slack 等）暴露统一 MCP 接口。
- **Capability negotiation**：MCP capabilities 字段告知客户端支持哪些功能（prompts/resources/sampling/tool_call 等），避免不兼容假设。
- **Tool schema evolution**：runWithModelFallback (model-fallback.js) 处理 compaction 失败，支持模型尝试不同的工具集。

### 4.3 关键文件清单

| 文件路径 | 用途 |
|---------|------|
| src/mcp/channel-server.ts | MCP 服务器创建、stdio transport 启动 |
| src/mcp/channel-bridge.ts | Gateway ↔ MCP 协议桥接 |
| src/mcp/channel-tools.ts | 工具注册和 MCP capabilities 配置 |
| src/agents/pi-bundle-mcp-tools.ts | MCP 运行时集成到 agent loop |
| src/agents/pi-bundle-mcp-runtime.test.ts | MCP 集成测试示例 |

---

## 5. 沙箱（Sandbox）

### 5.1 它做了什么

- **执行隔离方式**：
  - **Docker** (docker-backend.ts)：主流方案，创建临时容器，执行命令，销毁。支持自定义 image、volume mounts、network 模式。
  - **SSH** (ssh-backend.ts)：远程执行，通过 SSH 连接到另一台机器，执行命令。
  - **可插拔**：registerSandboxBackend (backend.ts) 允许注册自定义后端。
- **资源限制**：
  - CPU/内存：Docker backend 通过 --cpu/--memory 限制。
  - 超时：agents.defaults.sandbox.timeoutSeconds 控制，由 run loop 中的 AbortSignal 执行。
  - 磁盘：workspace mount 点限制（workspace-mounts.ts）。
- **文件系统隔离**：
  - fs-bridge.ts：模型可见的文件操作映射到沙箱目录。
  - fs-bridge-path-safety.ts：验证路径不逃出沙箱边界。
  - fs-bridge-mutation-helper.ts：rm/mv/cp 等操作的安全检查。
- **网络隔离**：network-mode.ts 配置容器网络（host/bridge/custom），SSH 沙箱通过 SSH 连接隔离。
- **多语言支持**：docker image 中包含 Python/Node.js/Bash 等环境，通过 execute 命令选择 shell。
- **执行超时与清理**：run-cleanup-timeout.ts 在超时时仍执行有界清理（flush session、close file handles）。

### 5.2 关键设计点

- **Factory + Manager pattern**：registerSandboxBackend 接受 factory function，optionally manager object（用于全局操作如健康检查）。
- **Config hash-based container reuse**：docker-backend 计算 config 哈希（config-hash.ts），相同 config 复用容器以加速。
- **Cross-session workspace sharing**：multiple agent runs 可共享 workspace（通过 host-paths.ts），需要额外的文件系统保护。
- **SSH backend 的远程透明性**：SSH backend 暴露与 Docker 相同的接口，在远程端执行，本地代码无感知。

### 5.3 关键文件清单

| 文件路径 | 用途 |
|---------|------|
| src/agents/sandbox/backend.ts | Sandbox backend 注册和工厂管理 |
| src/agents/sandbox/docker-backend.ts | Docker 沙箱实现 |
| src/agents/sandbox/ssh-backend.ts | SSH 沙箱实现 |
| src/agents/sandbox/fs-bridge.ts | 文件系统映射和操作 |
| src/agents/sandbox/fs-bridge-path-safety.ts | 路径安全验证 |
| src/agents/sandbox/fs-bridge-mutation-helper.ts | 文件操作的边界检查 |
| src/agents/sandbox/docker.ts | Docker 命令执行助手 |
| src/agents/sandbox/validate-sandbox-security.ts | 沙箱配置安全审计 |

---

## 6. 上下文压缩（Context Compression）

### 6.1 它做了什么

- **触发条件**：
  - 自动：context window 预计将在下一轮对话溢出（resolveEmbeddedCompactionTarget）。
  - 手动：用户执行 `/compact` 命令。
  - 失败触发：模型返回 context overflow 错误。
- **压缩算法**：
  - 主流：使用专用 compaction 模型（可配置为不同的 LLM）或同一 session 模型对历史进行总结。
  - Pluggable：registerCompactionProvider 允许自定义总结策略（如外部 API）。
  - 回退：如果 compaction 失败，使用内置 truncation（limitHistoryTurns）。
- **保留策略**（keep_tail）：
  - agents.defaults.compaction.keepRecentTokens：compaction 后保留最后 N tokens 的未压缩对话。
  - 通过 rotateTranscriptAfterCompaction 实现，创建新 transcript 文件。
  - Successor transcripts：压缩后的新 transcript 从摘要 + 未压缩尾部重建。
- **Tool pair 完整性**：shouldRotateCompactionTranscript/rotateTranscriptAfterCompaction 保证 tool_use/toolResult 配对不被切割。
- **压缩元数据**：
  - CapturedCompactionCheckpointSnapshot：压缩前后的快照（用于回滚）。
  - CompactionMessageMetrics：压缩前后的消息数/token 数。
  - resolveSessionCompactionCheckpointReason：记录压缩原因（overflow/manual/timeout）。

### 6.2 关键设计点

- **Token-aware split point**：compaction 使用 token count estimation 决定切割点，避免在 token 预算中间截断。
- **Identifier preservation**：identifierPolicy（strict/off/custom）控制是否在摘要中保留模型使用的标识符（如变量名）。
- **Transcript rotation**：truncateAfterCompaction 时创建新 .jsonl 文件，保留旧文件作为 checkpoint source，支持部分恢复。
- **Compaction hooks**：before_compaction/after_compaction hooks 允许插件观察和修改压缩决策。
- **Memory flush before compaction**：runPostCompactionSideEffects 在压缩前触发一个无声 memory flush turn，确保重要信息存到磁盘。
- **Context engine abstraction**：resolveContextEngine 支持多个 context backend（pi-agent-core 原生、custom），compaction 通过 context engine interface 调用。

### 6.3 关键文件清单

| 文件路径 | 用途 |
|---------|------|
| src/agents/pi-embedded-runner/compact.ts | Compaction 主流程、oversized transcript 处理 |
| src/agents/pi-embedded-runner/compaction-hooks.ts | Before/after compaction hooks 运行 |
| src/agents/pi-embedded-runner/compaction-runtime-context.ts | Compaction 目标和参数决策 |
| src/agents/pi-embedded-runner/compaction-successor-transcript.ts | Transcript 轮换和 keep_tail 实现 |
| src/agents/pi-embedded-runner/compaction-safety-timeout.ts | Compaction 超时保护 |
| src/agents/pi-embedded-runner/post-compaction-loop-guard.ts | Compaction 后进入死循环检测 |
| src/agents/pi-embedded-runner/compact-reasons.ts | Compaction 原因分类和诊断 |
| src/agents/pi-embedded-runner/tool-result-truncation.ts | Oversized tool result 截断策略 |
| docs/concepts/compaction.md | 压缩机制的完整文档 |

---

## 总结：值得借鉴的与值得规避的

### 值得借鉴的

1. **Attempt-based state machine**：将 agent run 分解为离散的 attempt，每个 attempt 返回规范化的结果对象，支持幂等重试和状态恢复。这比传统 callback 更易于理解和调试。

2. **Per-session + global lane 队列**：二级队列系统避免了全局瓶颈，同时保护了 session 一致性。priority（foreground/normal/background）和 timeout 参数提供细粒度控制。

3. **Plugin hook 系统的广泛应用**：before_model_resolve/before_prompt_build/before_agent_reply/before_tool_call/tool_result_persist 等多个钩点，让扩展功能无需修改核心代码。hook decision rules（block/cancel 的终止性）设计清晰。

4. **Auth profile 作为一等公民**：多 LLM provider/API key 支持，自动轮换和冷却机制（cooldown），避免了硬编码单一 API key 的局限。

5. **Tool pair 完整性保证**：在 compaction/truncation 时强制保持 tool_use/toolResult 配对，防止 model 收到单边的工具调用而无结果。

6. **Pluggable sandbox backend**：factory + manager 模式允许 Docker/SSH/自定义后端，支持混合部署（本地 Docker + 远程 SSH）。

7. **Successor transcript 的 keep_tail 策略**：压缩后不是简单地丢弃历史，而是创建新 transcript 从摘要 + 未压缩尾部重建，支持需要最近上下文的场景。

8. **Stage timing instrumentation**：attempt-stage-timing.ts 详细记录各阶段耗时，EMBEDDED_RUN_ATTEMPT_DISPATCH_STAGE 标记可用于诊断和 telemetry。

### 值得规避的

1. **Tool result 大小的多层控制**：tool-result-context-guard.ts（单工具）+ tool-result-truncation.ts（整 session）+ tool-result-char-estimator 形成多层依赖，导致代码分散且难以维护。应统一为单一 size policy 层。

2. **Compaction 的过度复杂性**：
   - before_compaction/after_compaction/runPostCompactionSideEffects 三个独立钩点。
   - CompactionTranscriptRotation 的多个条件分支。
   - PostCompactionLoopGuard 需要检查压缩后是否陷入死循环。
   
   建议设计阶段梳理压缩流程的状态机，减少条件分支和钩点数量。

3. **Error classification 的散落**：failover 原因分类分散在多个文件（classifyFailoverReason/isAuthAssistantError/isRateLimitAssistantError/parseImageDimensionError），应统一为单一 error codec module。

4. **MCP 集成的松耦合**：pi-bundle-mcp-tools.js 包裹 MCP 调用，失败时静默降级，可能掩盖 MCP 故障。建议显式错误传播和告警。

5. **Skill 的单次加载**：skill 在 session start 时一次加载，不支持动态重新加载。如果插件 skill 更新，需要重启 session，用户体验差。

6. **Context engine abstraction 的不完整**：pi-agent-core 原生和 custom context engine 的接口不完全对齐，导致某些压缩策略只适用一种后端。

### 建议

- 在自研 agent 框架时，**优先采纳 attempt-based state machine 和 plugin hook 系统**，这两个是核心竞争力。
- **避免重复设计** auth profile rotation、queue system、tool pair integrity 等，可以借鉴 openclaw 的做法并简化。
- **关注错误处理的可观测性**：classifyFailoverReason 和 stage timing instrumentation 都是值得参考的诊断机制。
- **压缩和截断需要早期统一设计**：不要在运行时才引入新的限制策略，避免像 openclaw 一样分散在多个文件。
