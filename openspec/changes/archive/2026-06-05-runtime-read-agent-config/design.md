## Context

阶段 1 后 `AgentFile` 已能承载治理/部署字段,但 runtime 仍读全局 `Settings`:`Settings()` 散见于
14 文件 21 处。读取分两类形态:
- **loop.py 的 `_resolve_*` 函数**:`call-param > Settings() > default` 模式(惰性 `from fleetent.config
  import Settings; s = Settings()`)。
- **模块级惰性 `Settings()`**:`budget.py`/`context.py`/`layered_budget.py`/`termination.py`/
  `sub_agent_lifecycle.py`/`session/manager.py`/`skills/registry.py`/`tools/*`/`intelligence/*`/
  `model/provider_health.py`/`observability/diagnostics.py`。

`AgentSnapshot`(`runtime/snapshot.py`)是 loop 消费的已解析配置,经 `_snapshot_from_file(AgentFile)`
构造,但当前**只带定义层字段**。standalone agent 进程是单 agent(`scan_home` → 单 forced-default);
多 agent 是 dev/平台态。

## Goals / Non-Goals

**Goals:**
- per-run 治理(预算/turn/压缩/loop/guardrail/permission gate/provider 熔断/tool·sub-agent 超时)
  随 per-request `AgentSnapshot` 解析生效。
- 进程级部署旋钮(session 清理间隔/disabled_skills/日志/microsandbox/image·vision/diagnostics)在
  agent 进程启动时从当前 agent 解析。
- 智能层切到读当前 agent 配置,消除字段空转。
- 砍掉 global 预算维度的运行时读取与聚合。
- 行为等价:未填字段解析结果 == 原 `Settings` 默认。

**Non-Goals:**
- 不删 `Settings` 任何字段(阶段 3)。切换后这些字段成死代码,阶段 3 清。
- 不动 DB/Alembic、不引新依赖。
- 不重写各 feature 的判定逻辑,只改配置**来源**。

## Decisions

### D1: per-run 治理走 snapshot,不走 `agent_config.current()`
**决定**:扩展 `AgentSnapshot` 携带 per-run 治理配置,loop 及其 helper 从传入的 snapshot 读。
**理由**:多 agent 态下 `agent_config.current()` 含多个 agent,per-run 配置必须跟随**该请求解析出的
agent**;snapshot 已是 per-request 解析产物,天然正确。备选(各处直接读 `current()`)在多 agent 态会
串配置。`_snapshot_from_file` 从 `AgentFile` 填;`_snapshot`(DB 授权侧)用 `Settings` 默认填,保持兼容。

### D2: 进程级部署旋钮走"启动时解析当前 agent",不进 snapshot
**决定**:session 清理间隔、disabled_skills、日志、microsandbox_url、image/vision endpoint、diagnostics
在 standalone agent 进程**启动时**从当前(单)agent 解析一次,注入到对应模块的可注入常量/构造参数。
**理由**:这些是进程级而非 per-request 的(后台维护循环、注册表、客户端单例),不随单条消息变化;
standalone 一进程一 agent,启动时解析即确定。多 agent 共享进程(仅 dev)时取默认,平台已不跑 loop,影响可控。

### D3: 解析优先级与默认来源
统一 `call-param > agent config > 字段默认`。字段默认本阶段仍取自/对齐 `Settings` 默认(阶段 3 后归一到
`AgentFile`)。loop.py 的 `_resolve_*` 把 `Settings()` 回退替换为读 snapshot 上的对应字段。

### D4: 智能层切换
`intelligence/**` 现 `from fleetent.config import VectorStoreSettings/EmbeddingSettings/...` 并 `Settings()`
取子配置。**决定**:改为从当前 agent 的 `vector_store`/`embedding`/`rerank`/`knowledge_base`/`long_term_ctx`
字段构造(这些子模型类型不变,仅来源变)。standalone 单 agent 经 `agent_config.current()`/启动注入获取。

### D5: 砍 global
删除 `layered_budget` 对 `agent_budget_global_*` 的读取与 global 桶聚合;聚合层从 4 跨运行层降到 3
(session/user/agent)。`Settings` 里的 `agent_budget_global_*` 字段阶段 3 删。

### D6: 切换粒度与 TDD
按读取点分组,每组先写"该配置来自 agent.yaml 而非 Settings"的失败测试再切。snapshot 扩展先行(其余
依赖它)。每组切换保持"未填 == 旧默认"的等价测试,守住行为不变。

## Risks / Trade-offs

- [21 处一次性切换,回归面大] → 分组 TDD,每组红绿独立;保留等价测试(未填字段 == 旧默认)兜底。
- [snapshot 字段膨胀] → 可接受;治理配置本就属于"运行该 agent 所需的已解析配置",归属 snapshot 合理。
- [多 agent 共享进程的进程级旋钮取默认,与单 agent 行为不同] → 平台已不跑 agent loop,此态仅 dev;
  design 显式声明,不视为缺陷。
- [`Settings` 与 snapshot 双来源并存的中间态] → 窗口短(到阶段 3);切换后 `Settings` 字段无人读=死代码,
  阶段 3 删除时有测试保证无回读。

## Migration Plan

- 行为向后兼容:现有 agent.yaml(未填治理字段)解析 == 旧全局默认,运行不变。
- 无 DB 迁移。
- 回滚:逐组 `_resolve_*`/模块读取还原到 `Settings()`,无数据影响。

## Open Questions

- 进程级旋钮在 standalone 的注入点(启动 wiring 具体落在 `fleetent agent run` boot 还是各模块 lazy
  首次解析)在 apply 时按模块既有形态择优,不阻塞 spec。

## 执行期决策(apply 时落实)
- **termination**:`resolve_limits` 已有 `config` 注入点;loop 的 `_build_controller` 经
  `_limit_config_from_governance(governance)` 注入,故 termination 的 max_turns/max_consecutive_failures
  已是 agent 来源(group 2 覆盖),termination 模块本身无需改。
- **context 压缩**:`maybe_compress`/`apply_anti_flap`/`compress_for_context_overflow` 已带 `agent_name`,
  故 `_default_config(agent_name)` 直接从 `agent_config.current().get(agent_name)` 的 context_* 字段解析,
  无 agent 时回退 Settings。无需把压缩字段塞进 GovernanceConfig(避免 ContextConfig 与 GovernanceConfig 二选一)。
- **sub_agent_timeout / sub-agent governance 继承**:本阶段**保留 Settings 回退**(`resolve_timeout` 的
  call-param > config > Settings 链不变,sub_agent 不注入 config)。理由:sub-agent 是 depth-1 helper,
  把 governance 从 parent loop 经 tool dispatch 穿到 `SubAgentExecutor` 的代价与收益不成比例。阶段 3 删
  Settings 时,`resolve_timeout` 与 `grace`/`_grace_defaults` 的 Settings 回退一并改为读 standalone 当前
  agent(或保留一个中性默认常量)——记为阶段 3 的收尾项。
- **grace call 预算**(`budget._grace_defaults`):同 sub_agent,暂留 Settings 回退,阶段 3 归一。
