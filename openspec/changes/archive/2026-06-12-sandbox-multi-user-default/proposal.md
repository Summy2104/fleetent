## Why

本项目**每个 agent 都服务多个终端用户**(不存在单用户 agent)。但 `sandbox-scope-split-followups` 把 `sandbox.multi_user` 默认设为 `false`(单用户),把"多用户"当作需显式开启的特例——与本项目现实相反。

后果:跨用户隔离护栏(多用户下 `workspace_scope: agent` → 纠正为 `session`)**默认处于关闭状态**。今天仍安全只因 `workspace_scope` 默认是 `session`(每用户隔离);但这是"默认值恰好安全",非结构性保证——一旦任何 agent 被配成 `workspace_scope: agent`,护栏因 `multi_user=false` 不触发 → 跨用户数据泄露。对一个全多用户的项目,安全姿态应反过来:**默认强制每用户隔离,要单用户复用才显式 opt-out**(fail-safe)。

## What Changes

- **`SandboxSettings.multi_user` 默认从 `false` 翻为 `true`**(fail-safe):每个 agent 默认按多用户处理——跨用户隔离护栏**永远在线**,任何配置的 `workspace_scope: agent` 都被纠正为 `session` 并告警。要单用户跨会话 agent-scope 数据复用,须显式声明 `sandbox.multi_user: false`(opt-out)。
- **该改动同时消解** `sandbox-scope-split-followups` 遗留的"platform 须记得写 `multi_user: true`"接线项——默认即安全,platform 无需任何接线。
- 纯 agent-runtime 侧默认值改动;`/workspace` 写入、镜像持久化(独立维度)不受影响。

## Capabilities

### Modified Capabilities
- `sandbox-workspace-scope`: 多用户信号默认翻转为 fail-safe——`sandbox.multi_user` 默认 `true`(每 agent 默认多用户/每用户隔离),显式 `false` 才退回单用户 agent-scope 数据复用;护栏默认在线而非默认关闭。

## Impact

- **代码**:`agent_config.py`(`SandboxSettings.multi_user` 默认 `True`)。`init_sandbox_manager` 已读该值传入,无需改。`resolve_workspace_scope` 护栏逻辑不变(仅其输入默认变安全)。
- **模块边界声明**:owning package=`agent_config`;public API surface=无变(字段已存在,仅默认值);owned tables=无;config namespace=`sandbox.multi_user`(默认值变更);cross-module dependencies=无新增,**不 import platform**;migration/shim=无代码迁移;**行为变更**:未显式配 `multi_user` 且配了 `workspace_scope: agent` 的 agent,其生效 scope 由 `agent` 变为 `session`(本就是安全方向;经 config_hash 触发容器重建,workspace 数据在宿主目录不丢)。
- **测试**:更新 `sandbox-scope-split-followups` 中断言 `multi_user` 默认 `false` / "未声明→agent 保留" 的用例为新默认(默认 `true`→agent 纠正 session;显式 `false`→agent 保留);新增"默认即 fail-safe"回归。
- **文档**:`agent.yaml.example` 说明 `multi_user` 默认 `true`(fail-safe)+ 单用户 opt-out 写法。
- **依赖**:基于已合并 main 的 `sandbox-scope-split-followups`(multi_user 字段 + 护栏 + 接线)。
