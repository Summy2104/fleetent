## 1. 前置核实（实现前的事实确认，无代码改动）

- [ ] 1.1 核实 `run_sync`（agent_loop.py ~194-201）/ `run_stream`（~225-230）现状提示组装：`full_system = f"{memory_ctx}\n\n{system_prompt}"` + 追加 matched skill，全拼进首条 system；确认 `match_skill` / `load_skill` / `load_memories` 的功能契约不变前提
- [ ] 1.2 核实目标后端（自托管 vLLM / OpenAI 兼容端点）对**多条 system 消息**与**前缀缓存**的行为，定 memory/skill 后置的承载形式（独立 system 消息 vs 首个 user turn 前缀）
- [ ] 1.3 核实各后端 `response.usage` 上提示缓存字段的命名/路径（Anthropic 风格 `cache_read_input_tokens`/`cache_creation_input_tokens`、OpenAI `prompt_tokens_details.cached_tokens`、vLLM 实际返回），定提取口径
- [ ] 1.4 确认 `log_run` 签名，新增 `cache_tokens: dict | None = None` 末位 kw 向后兼容（同 `stop_reason` 模式）；确认与 AR12 的"分层保留压缩"协调点（本 change 排 AR12 之后）

## 2. 提示组装重排（稳定前缀）

- [ ] 2.1 Write failing tests：构造两次"基础 system 相同、memory/skill 不同"的组装，断言基础 system 前缀部分逐字相同（差异仅在其后）；断言 memory 与 skill 内容仍在提示中（功能等价）。运行 `uv run pytest -x -q` 看到红
- [ ] 2.2 Implement：`run_sync` / `run_stream`（及 `run` 组装）改为 base system 作首条稳定 system 前缀、memory_ctx 与 matched skill 后置（按 1.2 定的承载形式）。看到绿

## 3. 缓存指标写入 trace

- [ ] 3.1 Write failing tests：mock `response.usage` 含缓存指标 → `log_run` 收到 `cache_tokens`；`usage` 不含缓存字段 → 不报错、不写该字段。看到红（先验证 log_run 尚未接收 cache_tokens）
- [ ] 3.2 Implement：`log_run` 增加 `cache_tokens: dict | None = None`（默认 None 向后兼容，非 None 写入 entry）；`run` / `run_stream` 收尾时从 `usage` 尽力提取缓存指标传入。看到绿

## 4. 后端无关守卫 + AR12 协调

- [ ] 4.1 Write failing tests：断言主循环 LLM 调用请求中**不含** provider 专有缓存标记（如 `cache_control`）——回归守卫，防误引入。看到红（或作为既有行为的防回归守卫）
- [ ] 4.2 确认/Implement：不注入任何缓存标记；在 design/注释标注"压缩保留可缓存头部"对 AR12 的协调要求（AR12 分层保留实现该保留，本 change 仅声明并依赖）。看到绿

## 5. 收尾

- [ ] 5.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`，项目要求）确认无回归（既有 agent_loop / 提示注入相关用例仍绿）
- [ ] 5.2 我的文件 `uv run ruff format src tests && uv run ruff check src tests` 全绿；`uv run mypy src` 不新增 mypy 错误模式
- [ ] 5.3 复核 memory/skill 重排后端到端功能等价（既有 skill 注入 / 记忆注入用例仍绿，仅位置变化）
