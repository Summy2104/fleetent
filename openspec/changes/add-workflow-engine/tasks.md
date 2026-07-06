# Tasks: add-workflow-engine

> 每个实现 task 严格 TDD：先写测试见红 → 实现见绿（`uv run pytest <file>::<test> -x -q`）。
> 分层：纯逻辑（解析/校验/就绪判定/映射）在 `tests/unit/`（mock LLM/DB）；真实 SQLite/迁移/引擎协作在 `tests/integration/`。
> 全程在 worktree 功能分支 `feat/add-workflow-engine` 进行，暂不合入 main。

## 1. 定义与校验（workflow-definition）

- [x] 1.1 [test][unit] workflow.yaml 解析：合法定义加载、type 专属字段缺失拒绝、未知字段拒绝（fail-closed）
- [x] 1.2 [impl] `workflow/definition.py`：yaml 解析 + 结构校验（name/inputs/steps/type 专属字段/timeout/retry 默认值）
- [x] 1.3 [test][unit] DAG 校验：Kahn 禁环（含自引用）、step id 唯一、`depends_on` 与 `${steps.*}` 引用存在性、数据引用自动隐含控制依赖
- [x] 1.4 [impl] 图构建与校验（控制边 ∪ 数据隐含边、成环报错含 step id 集合）
- [x] 1.5 [test][unit] tool schema 对照：未注册工具拒绝、必填参数缺失拒绝、字面量类型不符拒绝、`${}` 映射参数推迟运行期
- [x] 1.6 [impl] 对照 `tools.registry` schema 的 load 期校验
- [x] 1.7 [test][unit] 定义目录解析：`FLEETENT_WORKFLOWS_DIR` 覆盖、默认 `<config_dir>/workflows`、not-found 报错含可用列表（monkeypatch 路径）
- [x] 1.8 [impl] `paths.py` 增加 workflows 目录解析 + `load_definition` / 定义列举公开 API

## 2. 字段映射（运行期渲染）

- [x] 2.1 [test][unit] `${inputs.*}` / `${steps.<id>.output.*}` 点路径取值（dict key / list index）、独占占位符保留原类型、嵌入文本字符串化、未知命名根拒绝、路径不可解析 fail-closed（错误含占位符原文）
- [x] 2.2 [impl] `workflow/mapping.py`：占位符解析 + 点路径求值 + 渲染（无第三方依赖）

## 3. 持久化层（表与 store）

- [x] 3.1 [test][integration] embedded 迁移：全新 `agent_state.db` 建 `workflow_runs` / `workflow_step_runs` 两表；`set_state_db` 注入后 CRUD 可用；`start_run` 落 run 行 + 冻结 definition/principal + 预建全部 step 行（tmp_path，无 platform）
- [x] 3.2 [impl] `agent_state_migrations.MIGRATIONS` append 两表 + `workflow/store.py`（named parameters、retention 裁剪）
- [x] 3.3 [test][integration] 状态机与 claim：终态不可再迁移（非法迁移抛错）、并发 claim 条件 UPDATE 仅一方成功、`claimed_at` 过期回收 attempt+1（旧 attempt 失败留痕）
- [x] 3.4 [impl] store 状态迁移校验 + 幂等 claim + 过期回收

## 4. step 执行器（workflow-steps）

- [x] 4.1 [test][unit] tool step：渲染 args 后 dispatch、`ToolContext` 带外注入冻结 principal、输出 JSON 解析成功落对象 / 失败包 `{"text": ...}`、工具异常按 step 失败（mock dispatch）
- [x] 4.2 [impl] `workflow/steps.py` tool 执行器
- [x] 4.3 [test][unit] tool step 治理门控：`DIRECT` 执行、`APPROVAL`/`SANDBOX` 失败且错误含处置模式与建议、critical `REJECT` 恒拒（真 `action_gate` 纯函数 + 构造风险等级）
- [x] 4.4 [impl] 门控接入（`evaluate_risk_level → resolve_action_mode`，非 DIRECT 即失败）
- [x] 4.5 [test][unit] agent step：指定 `agent` 走快照（system_prompt/allowed_tools/model_policy）、省略用宿主、sub-agent 模式 + principal 继承、`awaiting_approval` 终止按 step 失败（mock `loop.run` / `snapshot.load_active`）
- [x] 4.6 [impl] agent 执行器
- [x] 4.7 [test][unit] output_schema：注入结构化指令、解析/校验失败重试一次、再失败落 `{"text": ...}`（mock loop 两次返回）
- [x] 4.8 [impl] 结构化输出（指令注入 + 解析 + 单次重试）
- [x] 4.9 [test][unit] notify step：显式 `to` 投递、省略回落 run origin、无可解析目标即 step 失败（mock outbound）
- [x] 4.10 [impl] notify 执行器（复用投递解析规则）

## 5. 执行引擎（workflow-engine）

- [x] 5.1 [test][unit] 就绪判定纯逻辑：全部控制前驱 succeeded 才就绪、任一前驱 failed/skipped/cancelled 级联 skip、run 终态判定（failed/succeeded/cancelled）
- [x] 5.2 [impl] `workflow/engine.py` 就绪/级联/终态纯函数
- [x] 5.3 [test][integration] 热路径端到端：三步线性链（假工具 + tmp DB）step 完成后立即推进（不等 sweep tick）、无依赖 step 并发受信号量上限约束
- [x] 5.4 [impl] 热路径步进直推 + 信号量（默认 4，`workflow.max_parallel` 覆盖）
- [x] 5.5 [test][integration] 冷路径与断点续跑：sweep 恢复孤儿 run、过期 claim 回收；模拟 kill（丢弃引擎内存态重建）后已成功 step 不重跑、run 续至终态
- [x] 5.6 [impl] sweep 循环 + 重启恢复
- [x] 5.7 [test][integration] 超时与取消：step 超时按 attempt 失败（retry=0 即终败级联）、run 取消 CancelToken 级联、剩余 step 置 cancelled
- [x] 5.8 [impl] 超时约束 + 取消传播（复用 `runtime/cancellation.py`）
- [x] 5.9 [test][integration] 冻结与终态投递：启动后改 yaml 不影响在跑 run；终态 best-effort 投递（deliver 优先→origin 回落、投递失败不改终态、CLI 无目标只记日志）；retention 裁剪
- [x] 5.10 [impl] 冻结快照读取路径 + 终态投递 + retention

## 6. 触发面与接线（workflow-triggers）

- [x] 6.1 [test][unit] `run_workflow` / `workflow_status` 工具：启动即返回 run_id（非阻塞）、未知 workflow 报错含可用列表、缺必填 inputs 拒绝且不落 run、status 返回逐 step 摘要、`workflow.enabled=false` 时工具不出现在 schema（mock store/start_run）
- [x] 6.2 [impl] `tools/builtin_tools.py` 注册两工具（origin 取自 ToolContext 会话来源）
- [x] 6.3 [test][integration] agent_app 接线：boot 时 `workflow.store.set_state_db` 注入 + 引擎随 lifespan 启停（owner-task、关停舱壁化）+ `workflow.enabled` 开关生效
- [x] 6.4 [impl] `agent_app` 接线 + `agent_config` 增加 `workflow.*` 配置解析
- [x] 6.5 [test][integration] CLI：`fleetent workflow list`（含非法定义标注校验错误不崩溃）、`fleetent workflow run --input k=v` 至终态输出逐 step 结果、与工具共用同一 `start_run` 入口
- [x] 6.6 [impl] CLI 子命令

## 7. 护栏与收尾

- [x] 7.1 [test] module-dependency 护栏：`fleetent.workflow` 纳入"禁 import platform"护栏断言（`test_module_dependency_guardrails.py`）
- [x] 7.2 示例 `workflows/demo.yaml` + `docs/capabilities/` 能力文档（非代码产物，人工确认后提交）
- [x] 7.3 收尾验证：`make test-pr` + `make test-integration-ci` 全绿（无新增失败）；无 platform 环境手工基线——`fleetent agent run` 起进程、CLI 跑 demo workflow、kill 重启验证断点续跑
