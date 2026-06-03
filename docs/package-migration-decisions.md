# flat→package 迁移：问题与决策日志

> 自主执行记录（2026-06-03 启动）。spec 规划见 PR #3（5 个 restructure-*-package change）。
> 串行顺序：sandbox✅（PR #98，前置范式）→ session → skills → model → tools → runtime。
> 审核人：张洋（全部完成后统一审核）。

## 规划阶段的关键决策（已写入各 design.md）

| 包 | 决策点 | 决策 |
|---|---|---|
| session | tests 里 monkeypatch `session_mgr.SESSIONS_DIR` 在 shim 上不生效（import * 复制引用），漏改会写真实 data/ | 强制把所有模块属性 patch 随迁到 `fleetent.session.manager`（design D5） |
| skills | `BUILTIN_SKILLS_DIR = Path(__file__).parent / "builtin_skills"` 移动后指向不存在的 `skills/builtin_skills` | 这是 5 包中唯一"非纯搬迁"修正：改为指向 `src/fleetent/builtin_skills/` 并加存在性自检（design D5） |
| model | `ROUTES` / `ROUTES_PATH` 是可变模块全局，测试大量 setattr | patch 一律操作 `fleetent.model.router` 模块属性，包级 re-export 仅供只读（design D2/D4） |
| tools | 旧 `tools.py` 与新包 `tools/` 同名，Python 不允许共存 → **无法留 shim** | `tools.py` 物理删除，兼容性与注册副作用由包 `__init__.py`（import builtin_tools）承担；全部调用方在同一 change 原子改完（design D2/D3） |
| tools | `session/manager` lazy import `_get_manager`，patch 包属性不影响真实模块 | 相关测试 patch 目标改 `fleetent.tools.builtin_tools`（design D5） |
| runtime | 39 处 patch 打在 `fleetent.agent_loop` 命名空间（18 个测试文件） | 分批随迁前缀到 `fleetent.runtime.loop`（符号名不变），每批跑对应测试文件（design D5） |
| 全局 | openspec CLI 在本环境不可用 | 按 sandbox 归档范式手工创建/归档 artifact，跳过 `openspec validate` 步骤 |

## 执行日志

### session（restructure-session-package）

- 状态：✅ 完成（**PR #4 已合并**，merge commit `a8aed1c`）
- 基线：1 failed / 2595 passed / 16 skipped（唯一失败为预存 `test_run_sync_passes_effective_sandbox_mode`，与 session 无关）；mypy 32 errors（预存）
- 收尾门禁：与基线逐项一致，零新增失败；9 个测试文件的 patch 目标已随迁；tests 中无旧 shim 路径残留
- 问题与决策：
  1. `gh pr merge --delete-branch` 因 main 被主 worktree 占用报 checkout 错——merge 本身已成功，手动删远程分支，结果一致
  2. **发现预存隔离缺陷**（与本迁移无关）：`tests/integration/test_cron_scheduler.py::test_fire_calls_agent_loop_run` / `test_fire_message_in_user_content` 只 patch `_agent_run` 未 patch `SESSIONS_DIR`，会泄漏 `data/sessions/cron/t1`、`t2`。按"纯搬迁"约束未触碰该无关测试，仅清理了泄漏文件。**→ 待办：建议后续单独提 fix PR 修复测试隔离**

### skills（restructure-skills-package）

- 状态：✅ 完成（**PR #5 已合并**，merge commit `5899382`）
- 门禁：pytest 1 failed / 2595 passed / 16 skipped（与基线完全一致）；mypy 32 errors 持平；ruff 干净
- 问题与决策：
  1. **名称遮蔽（偏离 design D2 的现场决策）**：design 原建议包级 re-export audit 域的 `audit/has_severe/Hit`，实测 re-export `audit` 函数会遮蔽同名子模块 `skills.audit`（`import fleetent.skills.audit as sa` 解析成函数），79 个测试报 AttributeError。**决策：`skills/__init__.py` 只导 registry 域符号，audit 域不做包级导出**，测试与包内引用直接走 `fleetent.skills.audit` 子模块。经验教训：包内有与公共函数同名的子模块时，二者不能同时出现在包命名空间——后续包注意（runtime 无此冲突，已核对）
  2. `BUILTIN_SKILLS_DIR` 修正为 `Path(__file__).parent.parent / "builtin_skills"`；覆盖测试因 autouse fixture 会 patch 该常量，改为独立从 `__file__` 推算真实路径断言存在性
  3. `skill_admin_api.py` 新 import 触发 ruff 排序错误，已修正

### model（restructure-model-package）

- 状态：✅ 完成（**PR #6 已合并**，merge commit `a665898`）
- 门禁：pytest 2 failed / 2594 passed——其中 1 个是预存基线失败，另 1 个 `test_tasks_run_concurrently_not_sequentially` 是**计时 flake**（全量套件 15 分钟高负载下 0.143s 超 0.13s 上限，单独跑通过；该测试自己的注释承认计时界限宽松）。实质与基线一致。mypy 32 持平；ruff 干净
- 问题与决策：无偏离 design。patch 随迁覆盖 conftest._cache、provider_health、agent_loop 测试中的 ROUTES/RouteConfig/RouteOverride 等，grep 确认 src+tests 零旧路径残留
- **→ 待办：`test_tasks_run_concurrently_not_sequentially` 计时上限过紧（0.13s），高负载下易 flake，建议后续放宽**

### tools（restructure-tools-package）

- 状态：✅ 完成（**PR #7 已合并**，merge commit `9c9dbd2`）
- 门禁：pytest 2595 passed / 1 failed（预存）与基线完全一致；`get_schemas()` = 12 与基线一致（**注册副作用链未断**）；mypy 32 持平；ruff 干净
- 问题与决策：
  1. 名称遮蔽核查：`__all__` 无与子模块同名符号；`vision_client.analyze` / `image_gen_client.generate` 不做包级 re-export，仅子模块访问，规避歧义
  2. design 只枚举了 mcp/client.py:210 一处 lazy import，实际还有 **905、933 两处** `import fleetent.tool_registry as tr`，一并改新路径
  3. **normalizer 暴露的源码 bug**：原代码经平铺 `tools.py` 调私有 `_save_upload`；包化后改为显式 `from fleetent.tools import builtin_tools` 后调用——私有跨界引用被显性化（行为不变）
  4. **docs/architecture.md 既有错误修正**：原把 vision_client/image_gen_client/multimodal 列在 `model/` 下，按蓝图已决归 `tools/`，更正两处包地图
  5. 多个测试经 shim `import *` 访问私有全局（`_registry`/`_connectors`/`MAX_TOOL_RESULT_BYTES` 等）会断（`import *` 不带下划线名），相关测试 import 改指真实子模块
  6. CLAUDE.md gotcha 已同步：`tools.py` → `tools/builtin_tools.py`，副作用经包 `__init__` 保留

### runtime（restructure-runtime-package）

- 状态：✅ 完成（**PR #8 已合并**，merge commit `c3babbb`）——蓝图 7 包全部落地
- 门禁：pytest 2595 passed / 1 failed（预存）/ 16 skipped 与基线逐项一致；`get_schemas()` = 12 持平；mypy 32 errors 零新增模式；ruff 干净；spec 四个 scenario 全部实测通过
- 问题与决策：
  1. **grep 列全后调用边比 design 枚举多 2 处**：`platform/admin_cli/agents.py`（load_active）、`integrations/mcp/client.py`（2 处 lazy error_classifier）——一并随迁。再次验证「动手前 grep 自查、不信任 design 枚举」的纪律
  2. **patch 面实测 48 处 / 14 文件**（proposal 估 39 处 / 18 文件），全模块引用合计 27 个测试文件。按「长名优先」机械替换 + 分批跑验证（治理 274 → normalizer 108 → test_agent_loop 158 → 集成 100）
  3. 测试里残留的 `setattr(agent_loop, ...)` 形式是 module-style 本地别名（已绑定真实 `fleetent.runtime.loop`），非 shim patch——与 model 包同范式，安全
  4. git rename 检测不显示 R（旧路径同 commit 改为 shim 内容），`git log --follow` 仍可追 blame——六包一致的已知现象
  5. CLAUDE.md / docs/architecture.md 已同步 runtime 新路径与 gotcha 表述

---

## 总结（2026-06-03，全部完成待审核）

**6 个 PR 全部合并**：#3（specs 规划）→ #4 session → #5 skills → #6 model → #7 tools → #8 runtime。蓝图 `runtime-package-blueprint` 定义的 7 个能力包（含先行的 sandbox，PR #98）全部落地。

最终结构：`runtime/`(13) `model/`(2) `tools/`(7) `skills/`(2) `session/`(2) `integrations/sandbox/`(7)，各包 `__init__.py` 收口公共 API；旧平铺路径仅剩 re-export shim（`tools.py` 因同名已物理删除）。

**每包门禁均与基线逐项一致**：pytest 2595 passed / 1 预存 failed / 16 skipped；mypy 32 errors（零新增模式）；`get_schemas()` = 12（工具注册副作用链全程未断）。

### 留给审核人的待办清单

1. **统一删 shim 收尾 change**（蓝图 D5 既定计划）：全库调用方已切新路径后，删除全部旧路径 shim
2. **预存测试隔离缺陷**：`tests/integration/test_cron_scheduler.py` 的 `test_fire_calls_agent_loop_run` / `test_fire_message_in_user_content` 未 patch SESSIONS_DIR，泄漏 `data/sessions/cron/t1`、`t2`——建议单独 fix PR
3. **预存基线失败**：`tests/unit/test_agent_loop.py::test_run_sync_passes_effective_sandbox_mode`（sandbox-mode 相关，迁移前即失败）——待排查修复
4. **计时 flake**：`test_tasks_run_concurrently_not_sequentially` 上限 0.13s 在全量高负载下偶发超时——建议放宽
5. openspec CLI 本环境不可用，各包 `openspec validate` 均以手工核验 spec scenario 替代——如需可补装后回放校验
