## 1. 前置核实（实现前的事实确认，无代码改动）

- [ ] 1.1 核实 `_summarize` 现状（context_mgr.py 行 146-169）：拼文本一次性摘、max_tokens=512、异常返回占位文本；`_compress`（行 115-118）把摘要包成 `[Earlier conversation summary]\n{text}` 的 system 消息，输出 `[*system_msgs, summary_msg, *tail]`（旧中段物理移除）
- [ ] 1.2 核实 `session_mgr.save` / `load`（session_mgr.py 行 30-42）：整列表 JSON 原子写（`.json.tmp → rename`）、`SESSIONS_DIR` 可 monkeypatch；确认累积摘要作为普通 system 消息原样往返，无需新增持久化结构、无需改 session_mgr
- [ ] 1.3 核实现有 system 消息形态，选不易撞车的来源标注前缀作为「累积摘要消息」的识别依据；确认 `maybe_compress`/`compress_for_context_overflow` 保持 `list → list` 签名（`prev_summary` 从入参 messages 提取，不引入 session_id 入参，不引入内部边界字段）
- [ ] 1.4 确认 AR13 三层切分中段边界（若已合入）；若未合入，确认本 change 退化为对现状 `to_summarize` 段增量摘要的契约一致

## 2. 摘要来源标注

- [ ] 2.1 Write failing tests：压缩产出的摘要消息文本含「历史对话摘要，仅供参考」含义的标注（声明为非新指令），不再是弱标注 `[Earlier conversation summary]`。mock `get_client_and_config`。运行 `uv run pytest -x -q` 看到红
- [ ] 2.2 Implement：摘要消息文本加固定来源标注前缀。看到绿

## 3. 增量摘要（已有摘要 + 新增中段）

- [ ] 3.1 Write failing tests：存在上一条累积摘要消息时，本次压缩从该消息提取 `prev_summary`，把「`prev_summary` + 当前中段」交 LLM 合并，不重摘已摘旧内容（旧中段已物理移除，当前中段即新增）；无累积摘要消息时退化为全量摘要。mock `get_client_and_config`，断言传入 LLM 的内容仅含 `prev_summary` + 当前中段。看到红
- [ ] 3.2 Implement：`_compress` 识别上一条摘要消息并提取 `prev_summary`，`_summarize` 支持「`prev_summary` + 当前中段 → 合并累积摘要」，无 `prev_summary` 时全量；不改 `maybe_compress` 签名。看到绿

## 4. 摘要失败降级（静态保留头尾 + 截断中段）

- [ ] 4.1 Write failing tests：mock `get_client_and_config` 使 LLM 调用抛异常 / 返回空，压缩 MUST NOT 抛异常；降级为保留头尾 + 截断中段，返回合法序列；降级被 log（不吞异常）。看到红
- [ ] 4.2 Implement：摘要失败走静态降级路径（不调 LLM，截断中段并标注），log 后返回兜底序列。看到绿

## 5. 累积摘要持久化往返（与 session_mgr 协调）

- [ ] 5.1 Write failing tests：压缩产生累积摘要消息后 `save` → `load` 往返（摘要为普通 system 消息，原样持久化回来），下一次压缩识别该摘要消息、提取 `prev_summary` 并在其上增量（不从头重摘）；不产生任何伴随文件 / DB 表 / 消息内边界字段。`monkeypatch session_mgr.SESSIONS_DIR` 隔离。看到红
- [ ] 5.2 Implement：压缩时按来源标注前缀识别上一条累积摘要消息并提取 `prev_summary`（无需改 session_mgr、无需新增持久化结构）。看到绿

## 6. 累积摘要不无限增长

- [ ] 6.1 Write failing tests：多次增量压缩后累积摘要受长度上界约束，不会无限增长到自身超过目标线投影。看到红
- [ ] 6.2 Implement：合并摘要 max_tokens 上界 + 超界整体重摘的收敛策略。看到绿

## 7. AR12 / AR13 既有行为回归

- [ ] 7.1 Write failing/regression tests：`Tmax` 触发 / 目标线回落、手动 force、错误触发入口、头尾完整保留与 tool-pair 完整性在增量摘要下不变。看到红或确认沿用既有用例
- [ ] 7.2 Implement / 确认：触发与目标线、分层切分、注入契约与 AR12/AR13 等价。看到绿

## 8. 收尾

- [ ] 8.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`，项目要求），确认无回归
- [ ] 8.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿
- [ ] 8.3 `uv run mypy src` 确认未新增 mypy 错误模式
