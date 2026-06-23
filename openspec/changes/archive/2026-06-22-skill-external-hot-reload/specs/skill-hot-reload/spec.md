## ADDED Requirements

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
