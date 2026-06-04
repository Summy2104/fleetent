## Context

flat→package 迁移（蓝图 `runtime-package-blueprint`）已全部落地，32 个旧扁平路径仅余 re-export shim。蓝图既定收尾步：统一删 shim。本 change 是纯删除 + 文档/spec 同步，无运行时逻辑改动，因此设计决策聚焦「如何安全删、如何防回归、如何消解两份 spec 的过渡态矛盾」。

## Goals / Non-Goals

**Goals**
- 物理删除 32 个 shim，使旧扁平路径彻底不可导入。
- 用回归测试固化「旧路径不可导入 + 新路径可达」这一终态。
- 同步两份 spec，使其反映终态而非过渡态。

**Non-Goals**
- 不改任何 src 运行时逻辑（不动 canonical 包内实现）。
- 不回改 `docs/` 下的 append-only 历史决策日志。
- 不动 `openspec/changes/archive/` 历史记录。

## Decisions

### 删除前确认 blast radius 为零
src 与 tests 对 32 个旧路径的引用（`from fleetent.<旧模块> import`、`import fleetent.<旧模块>`、字符串 patch 目标）均已为 0（前置 PR 已清零）。删除即安全，全量测试套件作回归网。

### 回归测试照抄 memory 先例
新测试结构对齐已存在的 `tests/unit/test_memory_legacy_import_cleanup.py`：
- `parametrize` 遍历 32 个旧模块全名，每个先 `sys.modules.pop(name, None)` 再断言 `importlib.import_module` 抛 `ModuleNotFoundError`。
- 正向用例抽查 6 个新包路径（`runtime`/`tools`/`model`/`skills`/`session`/`integrations.sandbox`）import 成功且各自一个代表性公共符号可达。

### spec 措辞从「仅为 shim」推进到「已移除」
- `package-architecture`：6 个「X 域已迁入」Requirement 各含一句「旧扁平路径 SHALL 仅保留为不承载逻辑的 re-export shim」+ 一个「旧扁平路径仅为 shim」Scenario。删 shim 后这两处变成假命题，必须改为「已移除、不再可导入」/「旧扁平路径已移除」（WHEN 导入旧路径 THEN ModuleNotFoundError）。其它 Scenario（公共 API 收口、行为不变、patch 目标已随迁等）保持不变。
- `module-boundaries`：已有 admin/governance/integrations/memory 的「Legacy X imports are removed」范式；其中 integrations 的 sandbox legacy scenario 删 shim 后即成真。为 runtime/model/tools/skills/session 补齐对应「legacy 导入已移除」需求，措辞对齐 line 138「Governance package migration」范式（`legacy ... shim modules SHALL NOT remain importable` + canonical 包存在 + legacy 导入失败）。

### module-boundaries 改动幅度：最小化新增一个聚合 Requirement
现有 module-boundaries 还有一条「Gradual migration with compatibility shim」Requirement 描述过渡期 shim 策略——它是 roadmap 级的通用策略陈述，不与「删 shim」终态直接矛盾（shim「MAY 保留」是迁移期措辞），保持不变以免扩大改动面。新增一条「Flat-path package migration cleanup」Requirement 聚合 runtime/model/tools/skills/session 五域的 legacy 移除断言即可，避免逐域复制大段文字。

## Risks / Trade-offs

- **风险**：某处遗漏的旧路径引用导致删除后 import 失败。**缓解**：删除前 grep 确认零引用；全量 pytest 作网；新回归测试正向断言新路径可达。
- **Trade-off**：module-boundaries 选择新增一个聚合 Requirement 而非逐域展开，换取最小改动面与可读性；若 review 认为需逐域独立 Requirement，可拆分，但不影响 validate 通过。
