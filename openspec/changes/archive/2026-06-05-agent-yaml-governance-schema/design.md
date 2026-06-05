## Context

`AgentFile`(`src/fleetent/agent_config.py`)已收下定义层、智能层(`vector_store`/`embedding`/
`rerank`/`knowledge_base`/`long_term_ctx`)、`mcp_servers`、`connectors`、`bindings`、`access`。
但运行治理与部署/进程旋钮仍只在全局 `Settings`(`src/fleetent/config.py`)。"配置全收口"
分三步:① 扩 schema(本 change) → ② runtime 切到读 agent config → ③ 删 `Settings` 残留。
本 change 故意只动 schema、不动行为,把高风险的接线/删除隔离到后续阶段。

## Goals / Non-Goals

**Goals:**
- `AgentFile` 能 per-agent 承载全部运行治理 + 部署/进程字段,默认值与现状等价。
- 复用 `config.py` 既有子模型,避免在两个文件里重复定义同一结构。
- 明确排除 `agent_budget_global_*` 与 `database_url`。
- 新字段纳入既有 `_reject_inline_secrets` 扫描。

**Non-Goals:**
- 不改任何运行时读取行为——runtime 仍读 `Settings`(阶段 2 才接线)。
- 不删除 `Settings` 任何字段(阶段 3)。
- 不引入新依赖、不动 DB / Alembic。

## Decisions

### D1: 分组用嵌套 block,还是平铺字段?
治理字段在 `Settings` 当前是平铺的(`agent_max_turns` 等)。`AgentFile` 已混用平铺
(`allowed_tools`)+ 嵌套(`vector_store`)。**决定**:治理旋钮平铺进 `AgentFile`(与
`Settings` 字段名一一对应,便于阶段 2 逐字段切换时对照);部署旋钮中已有子模型的
(`observability`/`diagnostics`/`mcp`/`scheduling`/`webhooks`)沿用嵌套子模型,标量的
(`microsandbox_url`/`log_format`/`image_gen_*`/`vision_*`/session 磁盘/`disabled_skills`)平铺。
理由:阶段 2 接线时 `agent_cfg.agent_max_turns` 与 `Settings().agent_max_turns` 同名,切换
是机械替换,减少出错面。备选(全嵌套到 `governance:`/`deployment:`)更整洁但放大阶段 2 改动量。

### D2: 子模型复用 vs 重定义
`AgentFile` 已 `from fleetent.config import EmbeddingSettings, ...`。**决定**:继续 import 复用
`ObservabilitySettings`、`DiagnosticsSettings`、`McpSettings`、`SchedulingSettings`、
`WebhooksSettings`。理由:避免双份 schema 漂移。注意阶段 3 删 `Settings` 时这些子模型需保留
(可能迁去 `agent_config` 或中性模块),本 change 不动其归属。

### D3: global 维度怎么"砍"
`extra="forbid"` 已在 `AgentFile.model_config`,因此**不新增** `agent_budget_global_*` 字段即等于
拒绝——yaml 里写了会 fail fast。`database_url` 同理(不加字段即拒绝)。无需额外校验代码。

### D4: 默认值来源
逐字段复制 `Settings` 当前默认(见 config.py:200-265)。用共享常量还是各写一遍?**决定**:
本 change 直接写字面默认(与 `Settings` 一致),阶段 3 删 `Settings` 后这些默认成为唯一真相源,
届时若要抽公共常量再处理。避免本 change 过早耦合两个 schema 的默认来源。

### D5: 内联密钥扫描覆盖面
`_reject_inline_secrets` 现扫 `mcp_servers`/`connectors` + 智能层的 `*_env`/`credential_ref`。
治理字段基本无密钥;部署字段里若未来有凭证类(暂无)走 `*_env`。**决定**:把新增的部署 payload
也并入扫描的 `intelligence_payload`-style 检查(按 `_is_secret_reference_key` 过滤),保证一致性,
即使当前无密钥字段也不留缺口。

## Risks / Trade-offs

- [字段先就位但空转,易误以为已生效] → 与现在智能层字段同样状态;在 proposal/spec 显式声明"本步
  不接线",阶段 2 负责接线;`config/agent.yaml.example` 注释标注。
- [平铺字段多,`AgentFile` 膨胀] → 可接受;阶段 2 切换需要逐字段对照,平铺反而降低映射成本。
- [默认值在 `AgentFile` 与 `Settings` 两处重复,可能漂移] → 本 change 到阶段 3 之间窗口短;阶段 3
  删 `Settings` 后归一。测试断言默认值等于 `Settings` 默认,捕捉漂移。

## Migration Plan

- 纯加字段,向后兼容:现有 `agent.yaml`(不含新字段)解析结果不变。
- 无 DB / schema 迁移。
- 回滚:还原 `AgentFile` schema 即可,无数据影响。

## Open Questions

- 无阻塞性问题。阶段 2 的接线顺序(先 runtime 还是先 intelligence)留待 `runtime-read-agent-config`
  的 design 决定。
