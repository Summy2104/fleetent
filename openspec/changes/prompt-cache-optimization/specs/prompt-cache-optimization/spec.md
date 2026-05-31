## ADDED Requirements

### Requirement: 稳定可缓存提示前缀

提示组装 SHALL 将稳定的基础 system prompt 置于消息序列最前作为可缓存前缀，将每请求/每轮可变的内容（记忆注入）置于其后。可变内容的变化 MUST NOT 改变基础 system 前缀，使自动前缀缓存得以在跨请求间命中。

> 注:可用 Skill 清单(`<available_skills>`)亦属稳定前缀的一部分,与基础 system 同处可缓存前缀(它仅随 Skill 集变化、对逐条请求稳定)——见 `skill-read-on-demand`。本 requirement 聚焦「基础 system + 稳定内容在前、逐请求可变的记忆在后」。

#### Scenario: 基础 system 前缀稳定于可变内容之前
- **WHEN** 两次请求的记忆注入不同、但基础 system 与 Skill 集相同
- **THEN** 两次组装出的消息序列的稳定前缀部分逐字相同，差异仅出现在其后的可变记忆内容

#### Scenario: 记忆仍生效（功能等价）
- **WHEN** 某请求有记忆上下文
- **THEN** 记忆内容仍包含在发给 LLM 的提示中（位于稳定前缀之后），其对模型的影响与重排前等价

### Requirement: 缓存命中指标写入 trace

当 LLM 响应的 `usage` 含提示缓存相关指标时，系统 SHALL 将其（如缓存读取 token、缓存创建 token、命中 token）记入运行日志（trace）。当后端未返回缓存指标时，MUST NOT 因此报错，trace 相应字段缺省即可。

#### Scenario: 有缓存指标时记入 trace
- **WHEN** 后端 `usage` 返回提示缓存命中/创建相关 token 指标
- **THEN** 该次运行的 trace 记录包含这些缓存指标

#### Scenario: 无缓存指标时安全降级
- **WHEN** 后端 `usage` 不含任何缓存指标字段
- **THEN** 运行正常完成，trace 不含缓存指标字段，不抛出异常

### Requirement: 后端无关、不使用 provider 专有缓存标记

提示缓存 MUST 依赖后端的自动前缀缓存能力实现，MUST NOT 使用任何 provider 专有的缓存标记（如 `cache_control`），也 MUST NOT 为此引入新的非 OpenAI 兼容 SDK。

#### Scenario: 不向请求注入缓存标记
- **WHEN** 主循环发起 LLM 调用
- **THEN** 请求中不包含 provider 专有的缓存控制标记，缓存命中完全依赖前缀稳定 + 后端自动缓存

### Requirement: 压缩保留可缓存头部

当上下文压缩改写消息历史时，MUST 保留可缓存的头部（基础 system 前缀），仅压缩对话尾部，避免压缩使前缀缓存失效。

#### Scenario: 压缩不改写可缓存前缀
- **WHEN** 上下文压缩被触发并改写历史
- **THEN** 基础 system 前缀部分保持不变，压缩只作用于其后的对话内容，前缀缓存不因压缩而整体失效
