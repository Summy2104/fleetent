# skill-hot-reload Specification

## Purpose
TBD - created by archiving change skill-hot-reload. Update Purpose after archive.
## Requirements
### Requirement: 运行期触发重扫无需重启

skill_registry SHALL 提供在服务运行期重新扫描 skills 目录、刷新索引的能力，且 MUST 可经 admin CLI 命令或管理 API 触发，无需重启服务。重扫完成后，后续到达的请求 MUST 反映重扫后的 Skill 集合（新增可被匹配、删除不再被匹配）。

#### Scenario: 重扫后新增 Skill 立即可用
- **WHEN** 服务运行期管理员新增一个 Skill 并触发重扫
- **THEN** 重扫后到达的请求能匹配并注入该新 Skill，无需重启服务

#### Scenario: 重扫后删除 Skill 不再匹配
- **WHEN** 服务运行期某 Skill 被移除并触发重扫
- **THEN** 重扫后到达的请求不再匹配该 Skill

### Requirement: 重扫期间原子切换，无半空索引窗口

重扫 SHALL 先把结果构建到一个新的索引对象，全部构建成功后再整体替换当前索引引用（原子切换）。在重扫进行中，任一读取索引的操作 MUST 要么看到完整的旧索引、要么看到完整的新索引，绝不会观察到部分填充的中间态。

管理 API 的 `engine_reload()` seam SHALL 调用 `skill_registry.reload()`（原子替换），不得调用 `skill_registry.scan()`（破坏性 clear+update 操作会在 clear 与 update 之间暴露空索引）。

#### Scenario: 重扫不暴露半空索引
- **WHEN** 重扫正在构建新索引的过程中有请求读取索引
- **THEN** 该请求看到的是完整的旧索引（构建尚未完成），而非被清空或部分填充的索引

#### Scenario: 构建完成后整体切换
- **WHEN** 新索引构建全部成功
- **THEN** 当前索引被整体替换为新索引，此后读取看到完整的新索引

#### Scenario: engine_reload 调用原子 reload
- **WHEN** 管理 API `POST /admin/skills/reload` 被调用
- **THEN** `engine_reload()` 调用 `skill_registry.reload()`，不调用 `skill_registry.scan()`
- **AND** 并发请求在重扫期间看到完整旧索引，重扫完成后看到完整新索引

### Requirement: 重扫失败保留旧索引并告警

当重扫过程中发生不可恢复错误（skills 目录不可用、批量解析失败等）时，skill_registry MUST 保留原有索引不变（不清空、不降级为空），并记录一条包含失败原因的结构化告警。重扫失败 MUST NOT 影响服务用旧索引继续匹配与注入。

#### Scenario: 重扫失败时旧索引保留
- **WHEN** 触发重扫但构建新索引过程中发生不可恢复错误
- **THEN** 原有索引保持不变，旧 Skill 仍可被匹配与加载，并记录一条含失败原因的告警

### Requirement: in-flight 任务继续使用旧版 Skill

已开始执行、已取用索引并注入 Skill 内容的请求，MUST 继续使用其取用时的 Skill 内容，不受重扫中途切换索引的影响。重扫 MUST NOT 改变已注入到某个进行中请求的 Skill 内容。

#### Scenario: 进行中的请求不被重扫篡改
- **WHEN** 某请求已取用并注入某 Skill 后，服务发生一次重扫（切换或失败）
- **THEN** 该进行中请求已注入的 Skill 内容保持不变，按取用时的旧版本完成处理

### Requirement: 自动感知外部文件变化并触发重扫

skill_registry MUST 提供一个轻量的「按需变化检测」能力 `refresh_if_changed(skills_dir)`：它 SHALL 遍历 user skills 根、对每个 `SKILL.md` 仅做文件元数据探测(修改时间 + 大小)拼出一个指纹清单(manifest)，与上一次已索引状态的指纹清单比对；**仅当**指纹清单发生变化时才触发既有的原子重扫 `reload()`，并返回是否发生了重扫。该检测 MUST NOT 读取或解析 SKILL.md 内容(只探测元数据)，使「无变化」这一常态开销保持在文件元数据探测级别。检测范围为 user skills 根(运行期 skill 变化发生处)；package 内置 skills 不纳入检测，但被触发的 `reload()` 仍按既有规则重扫内置+用户两源。

#### Scenario: 外部新增 skill 被自动感知
- **WHEN** 运行期有外部操作(手动新增、`git pull`、内网同步)在 user skills 根下新增一个 skill 目录，随后触发一次变化检测
- **THEN** 检测发现指纹清单变化并触发重扫，重扫后该新 skill 可被匹配/加载，无需重启

#### Scenario: 外部编辑 skill 被自动感知
- **WHEN** 运行期某个已索引 skill 的 `SKILL.md` 被外部编辑(内容改变导致 mtime 或大小变化)，随后触发一次变化检测
- **THEN** 检测发现变化并触发重扫，重扫后该 skill 反映新内容

#### Scenario: 外部删除 skill 被自动感知
- **WHEN** 运行期某个 skill 目录被外部删除，随后触发一次变化检测
- **THEN** 检测发现指纹清单变化并触发重扫，重扫后该 skill 不再被匹配

#### Scenario: 无变化时不重扫
- **WHEN** 触发一次变化检测但 user skills 根自上次索引以来无任何 `SKILL.md` 的新增/删除/元数据变化
- **THEN** 检测返回「未变化」，不触发重扫，仅做了文件元数据探测

#### Scenario: 指纹清单与已索引状态同源
- **WHEN** 完成一次 `scan()` 或 `reload()` 重建索引后立即触发变化检测且其间无文件变化
- **THEN** 检测判定为「未变化」(基线指纹清单由 scan/reload 同步维护，首次检测不误判为变化)

### Requirement: agent 侧每条入站消息在 catalog 注入前检测一次

agent 运行时 MUST 在每条入站消息组装 system prompt(注入 `available_skills_prompt` 清单)之前触发一次变化检测，使该消息及其 run 内的后续 skill 读取反映最新 skill 集合。该检测 MUST 每条入站消息至多一次，MUST NOT 在同一 run 的每次 LLM 调用或工具循环迭代中重复执行(一条 run 复用同一份已注入 catalog 的 system prompt)。检测所用的 skills 根 MUST 为该 agent 启动时扫描所用的同一 per-agent 根。

#### Scenario: 下一条消息反映外部变化
- **WHEN** 运行中的 agent 处理完一条消息后，外部修改了其 skills 目录，用户再发一条消息
- **THEN** 新消息在注入 catalog 前完成检测与(必要的)重扫，其 catalog 反映修改后的 skill 集合

#### Scenario: run 内不重复检测
- **WHEN** 一条入站消息触发的 run 内部进行了多轮 LLM 调用/工具循环
- **THEN** 变化检测在该 run 只执行一次(消息入口、catalog 注入前)，后续 LLM 调用不再重复检测

### Requirement: 自动热加载由 per-agent 配置门控且默认开启

agent 侧的「每条消息自动检测并热加载」MUST 受 per-agent 配置 `skill_hot_reload` 门控，且默认开启(`true`)。当某 agent 显式关闭(`false`)时，运行时 MUST NOT 在入站消息路径触发自动变化检测，行为退回到「仅启动时扫描一次 + 由 `skill_manage` 写操作触发的 reload」。

#### Scenario: 默认开启自动热加载
- **WHEN** 一个未显式设置 `skill_hot_reload` 的 agent 处理入站消息
- **THEN** 该消息在 catalog 注入前执行自动变化检测(默认行为)

#### Scenario: 关闭后退回启动期扫描
- **WHEN** 一个设置 `skill_hot_reload: false` 的 agent 处理入站消息，且其 skills 目录被外部修改
- **THEN** 运行时不在该消息路径触发自动检测，catalog 仍为启动时(或最近一次 reload 后)的 skill 集合

