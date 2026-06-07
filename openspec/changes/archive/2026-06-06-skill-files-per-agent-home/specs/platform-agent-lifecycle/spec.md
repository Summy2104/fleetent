## ADDED Requirements

### Requirement: Materialize 将平台 skill 文件分发到 agent home

为使 agent home 自包含（agent 进程只读自己的 home），`write_home()` SHALL 在写出 `agent.yaml` 与 `data/` 后，把平台全局 skills 目录（`skill_registry._resolve_skills_dir(None)`）下的全部 skill 目录复制到 `<home>/skills/`。

- 复制 SHALL 是幂等的（重复 materialize 覆盖同名文件，不报错）
- 当全局 skills 目录不存在时，复制 SHALL 被跳过，不抛异常
- 复制失败（IO 错误）SHALL 记录结构化告警但不阻断 materialize（agent.yaml 已写出）
- 全量复制：所有 skill 进入 home，运行时可见性由 agent.yaml 的 `allowed_skills` / `disabled_skills` 决定（文件分发与可见性解耦）

#### Scenario: skill 文件复制到 agent home

- **WHEN** 全局 skills 目录含 `crm-ops/SKILL.md`，对 agent "support" 触发 materialize
- **THEN** `<support-home>/skills/crm-ops/SKILL.md` 存在且内容与源一致

#### Scenario: 源目录缺失时安全跳过

- **WHEN** 全局 skills 目录不存在，触发 materialize
- **THEN** materialize 正常完成，`<home>/skills/` 不被创建（或为空），不抛异常

#### Scenario: 重复 materialize 幂等

- **WHEN** 对同一 agent 连续两次 materialize
- **THEN** 第二次覆盖 `<home>/skills/` 中的同名文件，不因目录已存在而报错
