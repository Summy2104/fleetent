## Context

`agent-definition` spec 已确立身份模型：`agents.id`=不可变身份/平台 FK 键，`agents.name`=可读标签且 runtime identity。v37 `finalize-agent-identity` 已把 `traces.agent_id` 列改名 `agent_name`。但运行时进程内载体（`AgentSnapshot`/`CommandContext`/`ModelPolicySnapshot`）与路径参数仍叫 `agent_id` 却装 name，外加 `agent_store.set_im_capabilities` 按 name 键、`read_projection:124` 参数名错位、布局文档自相矛盾。本 change 是收尾：让代码符合既有 spec。纯内部重命名 + 一处 store 键 name→id，无迁移/无 wire/无行为变更。

## Goals / Non-Goals

**Goals**
- 消除"字段/参数名叫 `agent_id` 却装 name"的认知陷阱，堵住误判身份模型跑偏。
- 平台 store 变更函数一律按 `agents.id` 键（修 `set_im_capabilities`）。
- 文档与 spec 表述自洽（name 作路径键）。

**Non-Goals**
- 不改磁盘目录键（保持 `agents/<name>/`，决策 F 不动）。
- 不引入 agent-local uuid（B 方案）。
- 不动 KB 队列死回落(#1)、by-agent 反查合并(#2)。
- 不加/恢复 rename 功能（YAGNI 不变）。

## Decisions

**D1：改名方向 = 让符号符合"实装值"，而非改值。**
运行时载体装的是 name（standalone agent 无 int id，解耦禁止依赖 platform id），故只能把 `agent_id`→`agent_name`，不能反过来把值改成 id。对平台 store 则相反：`set_im_capabilities` 的值本应是 id（平台侧有 id），故改成按 `agent.id`。判据 = "该侧本来该用哪个身份"：agent 侧=name、平台关系层=id。

**D2：`agent_name` 为统一命名。**
沿用 v37 先例（`traces.agent_name`）。路径/scope 参数（`tenant_agent_home_dir`/`agent_scope`）承载的是"agent 目录 handle = name"，同样用 `agent_name`，不用含糊的 `agent_handle`。

**D3：无 wire 影响，已核实。**
三个对象的 `agent_id` 字段均不进 HTTP 响应 / session 文件 / trace 落盘（trace 落的是独立的 `traces.agent_name` 列）；`ModelPolicySnapshot`/`AgentSnapshot`/`CommandContext` 仅进程内消费（connector scope、模型路由 label、命令分发）。故重命名为纯内部重构，不需版本化/兼容层。

**D4：spec 只动 `agent-definition`（收紧+防漂移），不新增 capability。**
两处 MODIFIED：给"身份"要求补"平台 store 按 id 键"场景（锚定 set_im_capabilities）；给"file-sourced runtime"要求补"运行时载体身份字段承载 name 且命名一致"场景（锚定字段重命名、防再漂移）。

## Risks / Trade-offs

- **改名波及调用点/测试面广** → 用 grep 全量定位每个符号的引用（含测试），逐符号改；每步跑受影响模块单测见绿。
- **`set_im_capabilities` 调用契约变化**（name→id）→ 仓库内唯一调用点 `agent_admin_api` 已 `_require_agent(name)` 拿到 agent 对象，改传 `agent.id` 即可；grep 确认无其它调用点。
- **误伤合法 `agent_id`（真装 id 的地方）** → 只改"实装 name"的那些符号（本 change 列名清单），平台关系层真 id 字段一律不动；靠 mypy strict + 单测防串。
- **文档改动与他人并发** → 布局文档为低频文件，冲突概率低；仍在收尾 merge 时 `git grep '^<<<<<<<'` 自检。

## Migration Plan

无数据迁移。纯符号重命名 + 一处 store 键调整。回滚 = revert commit。部署方无影响（无对外契约变更）。

## Open Questions

无。
