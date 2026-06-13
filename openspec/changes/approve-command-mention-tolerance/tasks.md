## 1. 纯函数（TDD，测试先行）

- [ ] 1.1 [test] `tests/unit/test_approval_mention_strip.py`：覆盖剥离 leading mention + 审批匹配——频道 `<@U123> approve <hex>` 命中、DM `approve <hex>` 命中、`<@U123|label> reject <hex>` 命中、`approve always <hex>` 命中、自然语言 `<@U123> approve the plan` 不命中、普通消息不命中——先见红
- [ ] 1.2 在 `normalizer.py` 实现 `_strip_leading_mention(text)`（`re.sub(r"^\s*<@[^>]+>\s*", "", text, count=1)`）+ 暴露可测的审批匹配入口（如 `_match_approval_command(text)`）——见绿

## 2. 接入 route

- [ ] 2.1 `normalizer.route`：审批匹配改为先剥离 leading mention 再 `_APPROVAL_RE.match`（复用 §1 纯函数），不改其余 resolve 逻辑
- [ ] 2.2 解耦校验：`normalizer` 不新增 import、不 `import fleetent.platform.*`；跑 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py`

## 3. 收尾

- [ ] 3.1 `make test-pr` 无新增失败 + 改动文件 ruff + `uv run mypy src` 通过
- [ ] 3.2 验证 agent/platform 解耦未破：`normalizer` 在无 platform 环境可 import（等价确认 `fleetent agent run` 路径不依赖 platform）
