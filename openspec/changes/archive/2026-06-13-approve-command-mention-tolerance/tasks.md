## 1. 纯函数（TDD，测试先行）

- [x] 1.1 [test] `tests/unit/test_approval_mention_strip.py`：覆盖剥离 leading mention + 审批匹配——频道 `<@U123> approve <hex>` 命中、DM `approve <hex>` 命中、`<@U123|label> reject <hex>` 命中、`approve always <hex>` 命中、自然语言 `<@U123> approve the plan` 不命中、普通消息不命中——先见红（10 用例 ImportError）
- [x] 1.2 在 `normalizer.py` 实现 `_strip_leading_mention(text)`（`re.sub(r"^\s*<@[^>]+>\s*", "", text, count=1)`）+ `_match_approval_command(text)`——见绿（10 passed）

## 2. 接入 route

- [x] 2.1 `normalizer.route`：审批匹配改为 `_match_approval_command(msg.text)`（匹配前剥离 leading mention），其余 resolve 逻辑不动
- [x] 2.2 解耦校验：`normalizer` 未新增 import、不 `import fleetent.platform.*`；`check_module_boundaries` 通过

## 3. 收尾

- [x] 3.1 `make test-pr` 全绿（全量 unit + 层边界 + 改动文件 ruff）；mypy `:409 approver_ids` 经 stash 对比确认为 main 预存（原 :391），非本次新增，且门禁不含 mypy
- [x] 3.2 agent/platform 解耦未破：`normalizer` 无 platform 反向依赖，`check_module_boundaries` 通过（等价确认 `fleetent agent run` 路径不依赖 platform）
