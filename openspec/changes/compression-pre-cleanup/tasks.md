## 1. 前置核实（实现前的事实确认，无代码改动）

- [ ] 1.1 核实 `_compress` 进入 `_summarize` 的位置（context_mgr.py 行 114）与摘要输入构造路径：`_summarize`（行 146-169）只摘 user/assistant、不摘 tool；膨胀源于 `_content(m)`（行 191-194）对整条 content 的 `str(...)`（**非** per-block `str(block)`），含 image 块的 content list 被整体字符串化。据此确认清理接入点为「构造摘要输入前替换 content list 内 image block」
- [ ] 1.2 核实 `estimate_tokens` 的 image 块判据（`block.get("type")=="image_url"`，行 49）与 `_IMAGE_BLOCK_TOKENS`，确认清理沿用同一识别口径、不改估算
- [ ] 1.3 核实工具调用记录在 messages 中的实际结构（assistant 消息的 `tool_calls`、对应 `role=="tool"` 消息的 `tool_call_id` 关联），定 block 粒度判等与「同工具 + 同参数 + 同结果」的规范化判等粒度（D3 Open）；必核「一条 assistant 含多个 tool_use block」的处置（仅当全部 block 等价才整删，否则保留）
- [ ] 1.4 核实图片 / 二进制占位块除 `image_url` 外是否有其它形态，定占位替换判据；确认尺寸元数据来源与缺失兜底（占位为 `[图片：{尺寸}]`，无时间戳维度——messages dict 无 timestamp 来源）

## 2. 图片 / 二进制占位兜底替换

- [ ] 2.1 Write failing tests：清理把 content list 内的图片 / 二进制占位块替换为 `[图片：{尺寸}]` 文本占位；尺寸缺失时用兜底值仍产出合法占位；替换后经 `_content` 字符串化的摘要输入不含 base64。运行 `uv run pytest -x -q` 看到红
- [ ] 2.2 Implement 图片占位替换辅助函数（纯函数，无副作用，缺失字段兜底）。看到绿

## 3. 重复工具调用去重

- [ ] 3.1 Write failing tests：同工具 + 同参数 + 同结果的 tool_call / tool_result 对仅保留最新一条；参数不同或结果不同的调用不去重；一条 assistant 含多个 tool_use block 且仅部分等价时保留整条、不误删非重复 block；去重后无孤立 tool_result、保留的 tool-pair 完整、序列对 LLM 合法。看到红
- [ ] 3.2 Implement 重复工具调用去重辅助函数（block 粒度严格全等判等，保留最新，成对去重，仅全 block 等价才整删消息）。看到绿

## 4. 清理阶段接入 _compress（毫秒级、不调 LLM）

- [ ] 4.1 Write failing tests：`_compress` 在进入 `_summarize` 前先清理待摘要内容；清理阶段 MUST NOT 触发 LLM —— mock `get_client_and_config`，断言清理过程中其调用次数为 0；清理产出再交摘要。看到红
- [ ] 4.2 Implement：在 `_compress` 调 `_summarize` 之前插入 `_pre_cleanup`（图片替换 + 去重），纯规则不调 LLM。看到绿

## 5. AR12 既有行为回归

- [ ] 5.1 Write failing/regression tests：`Tmax` 触发 / 不触发、目标线回落、手动 force、错误触发入口、尾部 tool-pair 完整性在清理插入后不变；清理只作用于待摘要内容，不改触发判定。看到红或确认沿用既有用例
- [ ] 5.2 Implement / 确认：触发与目标线、注入契约与 AR12 等价。看到绿

## 6. 收尾

- [ ] 6.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`，项目要求），确认无回归
- [ ] 6.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿
- [ ] 6.3 `uv run mypy src` 确认未新增 mypy 错误模式
