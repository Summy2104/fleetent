## 1. 前置核实（实现前的事实确认，无代码改动）

- [x] 1.1 核实 `_compress` 现状切分（context_mgr.py 行 103-120）：`system_msgs` / `conv_msgs` 二分、`_select_tail` 反推尾部、`to_summarize = conv_msgs[:len-len(tail)]`、组装顺序 `[*system_msgs, summary_msg, *tail]`
- [x] 1.2 核实 `_select_tail` 的 `fixed = estimate_tokens(system_msgs) + _SUMMARY_OVERHEAD_TOKENS`（行 137）与下界 1 条逻辑，确认扩展为「头部完整层」后投影口径仍自洽
- [x] 1.3 核实 `_keep_tail` 的 identity check（`m is tail[0]`，行 177）与 tool-pair 完整性，确认头部去重也必须用 `is` 而非 `==`（CLAUDE.md gotcha）
- [x] 1.4 用现有 `tests/test_context_mgr.py` 样例核实「开头连续 user 段」的实际形态，确认默认上界 2 的表现（已定：默认 2，经 `Settings.compression_initial_intent_max` 可配置）；核实 `config.Settings` 字段添加方式（config.py）以承载该上界

## 2. 初始意图识别（头部范围）

- [x] 2.1 Write failing tests for 初始意图识别：从非 system 消息开头起取连续 `user` 段（遇首条非 user 即停），受默认上界限制；「开头非 user」「无 user」边界返回空初始意图。运行 `uv run pytest -x -q` 看到红
- [x] 2.2 Implement 头部识别辅助函数（system 消息 + 开头连续 user 段，按原顺序，受上界约束，默认 2，上界可经 config dict / 参数注入），看到绿
- [x] 2.3 Write failing test for 配置项：`Settings().compression_initial_intent_max` 默认 2、可被环境变量 / `config/settings.yaml` 覆盖；覆盖后头部识别按新上界生效。看到红
- [x] 2.4 Implement：`config.py` 新增 `compression_initial_intent_max: int = 2` 字段，压缩入口把该值经 config dict 透传给头部识别；`config/settings.yaml.example` 补注释示例。看到绿

## 3. 三层切分与组装（_compress）

- [x] 3.1 Write failing tests：压缩后初始意图消息完整保留且 MUST NOT 出现在摘要文本输入中；最终序列顺序为 `[头部完整..., 摘要, 尾部完整...]`；中段（既非头部也非尾部）才进 `_summarize`。mock `get_client_and_config`，断言传入摘要的消息不含初始意图。看到红
- [x] 3.2 Implement `_compress` 三层切分：析出头部（system + 初始意图）、尾部（`_keep_tail`）、中段（其余），组装 `[*head, summary_msg, *tail]`。看到绿

## 4. Tretained 目标线投影纳入头部

- [x] 4.1 Write failing tests：`fixed` 投影含头部完整层（system + 初始意图）token；头部较大时尾部相应收缩但保 1 条下界与 tool-pair 完整，压缩后估算 token 回落到 `Tretained` 附近或以下。看到红
- [x] 4.2 Implement：`_select_tail` 的 `fixed` 从 `system_msgs` 扩展为 `head`。看到绿

## 5. 退化场景兜底（中段为空 / 头尾重叠）

- [x] 5.1 Write failing tests：会话过短致中段为空时不生成空摘要消息、直接返回 `[*head, *tail]`；头尾重叠的同一条消息用 identity check 去重保留单份、维持原顺序；序列对 LLM 合法。看到红
- [x] 5.2 Implement：中段为空跳过摘要；头尾用 `is` 去重。看到绿

## 6. AR12 既有行为回归

- [x] 6.1 Write failing/regression tests：`Tmax` 触发 / 不触发、手动 force 触发、错误触发入口、尾部 tool-pair 完整性等 AR12 既有行为在三层切分下不变。看到红或确认沿用既有用例
- [x] 6.2 Implement / 确认：触发与目标线语义、注入契约与 AR12 等价。看到绿

## 7. 收尾

- [x] 7.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`，项目要求），确认无回归
- [x] 7.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿
- [x] 7.3 `uv run mypy src` 确认未新增 mypy 错误模式
