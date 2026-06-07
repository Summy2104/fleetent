## Why

同名 skill 冲突当前由纯路径字典序决定胜者（`skill-name-conflict` SK8），不区分来源。后果：operator 无法可预测地用自定义 user skill 覆盖一个 builtin skill——胜负取决于绝对路径排序这个实现意外，而非意图。openclaw 的多层 precedence、hermes 的 `~/.hermes/skills` 覆盖都给了明确的"后层覆盖前层"语义；fleetent 缺这一层。

## What Changes

- `_scan_dir` 同名冲突解析改为**层级优先**：user skill（`builtin=False`）覆盖 builtin skill（`builtin=True`），与路径排序无关
- 同层级内（两 builtin 或两 user）仍按既有路径字典序决定胜者（SK8 不变）
- 冲突告警新增 `tier_override` 标志，便于运维区分"层级覆盖"与"同层路径排序"

## Capabilities

### New Capabilities

无新 capability。

### Modified Capabilities

- `skill-name-conflict`：在路径字典序规则之上叠加层级优先（user 覆盖 builtin），同层级保持路径排序

## Impact

- **修改文件**：`src/fleetent/skills/registry.py`（`_scan_dir` 冲突分支）
- **测试**：`tests/unit/test_skill_registry.py`（user 覆盖 builtin、同层路径排序不变、告警含 tier_override）
- **无破坏性变更**：同层级行为完全不变；仅跨层级（user vs builtin）从"路径排序"改为"user 胜"，这是更符合直觉的语义
