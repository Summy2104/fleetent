## Context

本项目所有 agent 均服务多用户。`sandbox-scope-split-followups` 把 `multi_user` 默认设为 `false`,使跨用户隔离护栏默认关闭——与项目现实相反。现状已核实:`agent_config.py:295` `multi_user: bool = False`;`config.py:38` `_DEFAULT_SCOPE = "session"`(故今天默认仍每用户隔离、不漏,但护栏靠默认值巧合而非结构保证)。

## Goals / Non-Goals

**Goals:** `multi_user` 默认翻为 `true`(fail-safe),护栏结构性常开;单用户需求经显式 `false` opt-out;消解 platform 接线遗留项。

**Non-Goals:** 不改护栏逻辑 `resolve_workspace_scope`(已正确);不删 agent 数据档枚举(显式 opt-out 仍可单用户用);不动镜像持久化/加固。

## Decisions

### D1:翻默认而非删 agent 数据档
仅把 `SandboxSettings.multi_user` 默认 `False→True`。护栏(已存在)对默认 `true` 即对任意配置的 `workspace_scope: agent` 纠正为 `session`,达到"全多用户项目结构性每用户隔离"。
- **备选**:彻底删除 `workspace_scope: agent` 数据档(只剩 session)。否决——更大改动,且产品层面其他单用户部署仍可经显式 `multi_user: false` 合法使用 agent 数据复用;翻默认已满足本项目安全目标且保留产品弹性。
- **备选**:不改代码默认,只在 agent.yaml 模板写 `multi_user: true`。否决——依赖每处模板/生成都记得写,非结构保证;安全特性应 fail-safe 默认安全、显式 opt-out。

## Risks / Trade-offs

- **行为变更**:未显式配 `multi_user`、且配了 `workspace_scope: agent` 的 agent,生效 scope 由 `agent` 变 `session`。→ 这是安全方向的变更;数据在宿主 workspace 目录不丢,经 config_hash 触发容器重建。本项目无单用户 agent,实际影响仅"挡掉误配"。
- **单用户复用回归**:真单用户若想 agent-scope 复用,须显式 `multi_user: false`。→ 文档化 opt-out 写法。

## Migration Plan

无 DB 迁移。默认值变更即生效;存量 agent-scope 容器经 config_hash 重建。Rollback:回滚默认值。

## Open Questions

无。
