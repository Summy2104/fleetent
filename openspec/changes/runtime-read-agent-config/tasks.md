## 1. AgentSnapshot 扩展携带治理配置(其余任务依赖)

- [x] 1.1 Write failing tests: 断言 `_snapshot_from_file(AgentFile)` 产出的 snapshot 携带治理字段
      (agent_max_turns、context 压缩组、分层预算 session/user/agent、permission gate、provider 熔断、
      tool/sub-agent 超时);断言 DB 侧 `_snapshot` 用旧默认填充保持兼容。运行见红
- [x] 1.2 扩展 `AgentSnapshot`(`runtime/snapshot.py`)字段 + `_snapshot_from_file` / `_snapshot` 填充。
      运行见绿

## 2. loop.py 治理来源切换

- [x] 2.1 Write failing tests: 断言 `agent_max_turns` 等来自 snapshot/agent 配置(未注入参数时),
      优先级 call-param > agent config > default;未填字段 == 旧 `Settings` 默认。运行见红
- [x] 2.2 把 `_resolve_budget_config`/`_resolve_loop_config`/`_resolve_guardrail_threshold`/
      `_resolve_parallel_max`/`_resolve_default_tool_timeout` 的 `Settings()` 回退改为读 snapshot。运行见绿

## 3. 跨运行预算 + 砍 global

- [x] 3.1 Write failing tests: 断言聚合检查只覆盖 session/user/agent 三层、无 global 桶;窗口默认与来源
      来自 agent 配置;key 缺失跳过该层。运行见红
- [x] 3.2 改 `layered_budget.py` 读 agent 配置、移除 `agent_budget_global_*` 读取与 global 聚合;
      `budget.py` token 维度来源切换。运行见绿

## 4. termination / context / sub_agent 来源切换

- [x] 4.1 Write failing tests: `termination.py`、`context.py`(压缩阈值/keep_recent/各 ratio)、
      `sub_agent_lifecycle.py`(sub-agent 超时)来自 agent 配置;未填 == 旧默认。运行见红
- [x] 4.2 切换上述模块的 `Settings()` 读取到 agent 配置。运行见绿

## 5. 智能层来源切换(消除空转)

- [x] 5.1 Write failing tests: vector_store/embedding/rerank/knowledge_base/long_term_ctx 运行时从当前
      agent 配置构造,而非全局 `Settings`(rig `Settings()` 抛错验证不再回读)。运行见红
- [x] 5.2 切换 `intelligence/**`(vector_store/embeddings/rerank/runtime、knowledge_base/*、
      long_term_ctx*、memory/store、reflection)读取来源。运行见绿

## 6. 进程级部署旋钮启动时解析

- [x] 6.1 Write failing tests: standalone agent 进程下 session 清理间隔/disabled_skills/microsandbox_url/
      image·vision endpoint/diagnostics/日志来自当前 agent 配置;多 agent 态回退默认。运行见红
- [x] 6.2 切换 `session/manager.py`、`skills/registry.py`、`tools/{image_gen_client,vision_client}.py`、
      `observability/diagnostics.py`、`model/provider_health.py` 的来源(启动注入或 lazy 解析当前 agent)。
      运行见绿

## 7. 收尾

- [ ] 7.1 `uv run ruff format src tests && uv run ruff check src tests` + `uv run mypy src` 通过
- [ ] 7.2 全量 `uv run pytest -x -q` 与 `uv run python scripts/check_test_layers.py` 通过
- [ ] 7.3 确认 `Settings` 字段已无运行时回读(grep 验证;为阶段 3 删除铺路),并在 change 完成说明中列出
      此时已成死代码的 `Settings` 字段清单
