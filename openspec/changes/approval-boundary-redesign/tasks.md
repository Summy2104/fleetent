## 1. 中心裁决入口 approval_policy（地基）

- [ ] 1.1 [test] `tests/unit/test_approval_policy.py`：`risk_for` 骨架——非外发工具返回其注册静态档（如 run_code→medium）、无法解析当前对话地址时 fail-closed→medium、`tool_args` 内 `risk`/`risk_level` 字段被忽略（反逃逸）。先见红。
- [ ] 1.2 [impl] 新建 `governance/approval_policy.py`，`risk_for(tool_name, args, tool_context) -> str`：默认委托注册静态档，分发到内置工具/ MCP 裁决钩子；`governance` MUST NOT import platform。见绿。
- [ ] 1.3 [test] 接线测试：`registry.evaluate_risk_level` 与 `runtime/loop.py` dispatch 委托 `approval_policy.risk_for`（patch 验证调用与回传）。先见红。
- [ ] 1.4 [impl] 改 `registry.evaluate_risk_level` / loop dispatch 委托 `approval_policy.risk_for`（保留异常 fail-closed→medium 语义）。见绿。

## 2. send_im_message 接收方身份动态定级

- [ ] 2.1 [test] `risk_for("send_im_message", args, ctx)`：`(target,target_type)`==当前对话地址（同一 DM 用户 / 同一频道）→none；他人/他群→medium；无法解析地址→medium。先见红。
- [ ] 2.2 [impl] `send_im_message` 去掉静态 `risk_level="medium"`，改由 `approval_policy` 按接收方身份裁决；实现"当前对话地址解析"（取自 `session_context`）。见绿。

## 3. send_file 恒免审批 + 跨 scope 硬拒绝

- [ ] 3.1 [test] `risk_for("send_file", …)` 恒返回 none；`_send_file_risk` callable 已移除（无 dynamic risk）。先见红。
- [ ] 3.2 [impl] `send_file` `risk_level` 由 callable 改为静态免审批，删除 `_send_file_risk`。见绿。
- [ ] 3.3 [test] integration：`send_file` 解析 `/exchange` 跨 scope 工件 → 硬拒绝（返回说明文本、文件未发、不触发审批升级）；本 scope 工件正常发；LOW 工具跨 scope 仍拒绝；`send_im_message` 已审批 files 跨 scope 仍放行。先见红。
- [ ] 3.4 [impl] 调整 `artifact_exchange`/`builtin_tools` send_file 路径：去掉 send_file 的跨 scope 审批逃生分支（`resolve(... approved=...)` 对 send_file 不再有 approved 豁免），保留 send_im_message files 已审批路径。见绿。

## 4. invoke_agent 免审批

- [ ] 4.1 [test] `risk_for("invoke_agent", …)` 返回 none；dispatch 不前置审批门。先见红。
- [ ] 4.2 [impl] `invoke_agent` 去掉静态 `risk_level="medium"`（经 approval_policy 归 none）。见绿。

## 5. MCP approval_rules 配置 + 评估

- [ ] 5.1 [test] `agent_config` 解析 `mcp_servers[].approval_rules: [{tool, when?}]`（含缺省、空、多规则）。先见红。
- [ ] 5.2 [impl] `agent_config` 增 `approval_rules` dataclass + 解析。见绿。
- [ ] 5.3 [test] `risk_for` MCP 裁决单测：未配置→none；`tool`+`when` 命中→medium；省略 `when`=整工具 medium；多参数 AND；参数未命中→none。先见红。
- [ ] 5.4 [impl] `approval_policy` MCP 规则匹配（按 `{server}__{tool}` + args）；`integrations/mcp/client.py` 注册时把该 agent 的 approval_rules 交给 `approval_policy`。见绿。

## 6. google-workspace 发件默认审批规则

- [ ] 6.1 [test] 未配置 approval_rules 时：`manage_email` `operation∈{send,reply,replyAll,forward}`→medium、`operation=search/read`→none；agent.yaml 显式配置可覆盖默认。先见红。
- [ ] 6.2 [impl] 内置 `google-workspace` 默认规则（可被 agent.yaml 覆盖）。见绿。

## 7. 旧契约改写与收尾

- [ ] 7.1 [test+impl] 改写依赖旧"恒 medium"假设的现有测试（send_im_message / send_file / invoke_agent 的旧 risk 断言）使之符合新接收方身份契约。
- [ ] 7.2 [docs] agent.yaml `mcp_servers[].approval_rules` 配置文档 + 显著标注"MCP 未声明即免审批"的安全取舍 + 内置 email 默认规则说明。
- [ ] 7.3 [gate] `make test-pr` 全绿；`uv run pytest tests/integration -q` 对照 main 基线无新增失败。
- [ ] 7.4 [gate] `uv run mypy src`（≤基线）+ 改动文件 `ruff check/format` 净。
