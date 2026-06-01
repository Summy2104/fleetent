## Why

`skill_registry.scan()`（行 31-56）在两个时机运行：FastAPI lifespan 启动时（`server.py` 行 68）和 CLI 路径 `run_sync()` 每次调用时（`agent_loop.py` 行 408，`run_sync` 内 `scan_skills()`；`run()` 自身不扫描、不注入 Skill）。HTTP 服务一旦启动，索引就**只在进程启动那一次构建**——管理员新增 / 修改 / 删除一个 Skill 后，必须**重启整个服务**才能让变更生效。这与 v1.0「运行中新增 Skill 立即生效」（skill.md 验收场景 4）相悖。

更糟的是 `scan()` 的实现方式不适合运行期重扫：它先 `_index.clear()` **就地清空**全局索引，再逐个 `glob` 读文件填充。若在服务运行期直接复用它重扫，存在两个问题：

- **重扫期间索引处于半空状态**：`clear()` 之后、填充完成之前，并发到达的请求可能匹配到一个不完整的索引，命中率骤降。
- **重扫失败无回滚**：某个 SKILL.md 在重扫途中读取/解析抛错，`_index` 已被 `clear()`，旧索引永久丢失，服务降级为「无 Skill」。

本 change 落实 docs/capabilities/skill.md「规划中」的**热加载**：经 admin CLI / 管理 API 触发重扫，无需重启；重扫期间继续用旧索引、完成后**原子切换**；重扫失败保留旧索引并告警；正在执行中的任务继续用旧版 Skill 不受影响。

## What Changes

- 新增**运行期重扫入口**：提供 `reload()`（或等价函数），在不重启服务的前提下重新扫描 skills 目录并刷新索引。
- **构建到临时索引 + 原子切换**：重扫先把结果构建到一个**新的局部索引对象**，全部成功后**整体替换**模块级索引引用（原子赋值），杜绝「半空索引」窗口。`scan()` 的就地 `clear()+填充` 不再用于运行期重扫路径。
- **失败保留旧索引并告警**：重扫过程中若发生不可恢复错误（目录消失、批量解析失败等），**保留旧索引不变**并记录结构化 warning，服务不降级。
- **in-flight 任务不受影响**：已开始执行、已读取过索引/已注入 Skill 的请求，继续使用其取用时的 Skill 内容，不被重扫中途篡改（依赖原子整体替换 + 注入发生在请求早期一次性取用）。
- 暴露**触发通道**：新增 admin CLI 子命令（如 `reload-skills`）与/或管理 API 端点触发 `reload()`；返回重扫结果摘要（新增/变更数量或成功/失败）。

## Capabilities

### New Capabilities
- `skill-hot-reload`: 运行期经 admin CLI / 管理 API 触发 Skill 索引重扫——构建到新索引后原子整体切换（无半空窗口）、重扫失败保留旧索引并告警、in-flight 任务继续用旧版 Skill 不受影响。

### Modified Capabilities
<!-- 无既有 spec 的需求级行为变更。启动时 scan() 的行为与关键词匹配/注入不变；本次新增运行期 reload() 与原子切换语义，并将运行期重扫从「就地 clear+填充」改为「构建到新索引后替换」。热加载此前无既有 spec 承载，故收口在本新 capability 内。 -->

## Impact

- **代码**：
  - 修改 `src/fleetent/skill_registry.py`：抽出「扫描目录 → 构建索引对象」的纯构建逻辑（不触碰全局 `_index`）；新增 `reload(skills_dir=None)` 调用该构建逻辑得到新索引，成功则原子替换模块级索引引用，失败保留旧索引并 warning。`scan()` 在启动路径仍可用（首次构建可走同一构建逻辑）。
  - 修改 `src/fleetent/server.py`：可选新增管理 API 端点（Bearer 认证）触发 `reload()` 并返回结果摘要。
  - 修改 `src/fleetent/admin.py`：新增 `reload-skills` 子命令（沿用既有 `add_parser` 模式），触发重扫并打印结果。
- **配置**：无新增 Settings 字段；触发通道复用既有 admin/server 认证。
- **测试**：扩展 `tests/test_skill_registry.py`（`reload` 后索引反映新增/删除的 Skill；重扫失败时旧索引保留；重扫不经历半空窗口——构建在替换前完成）；admin/server 触发路径的轻量测试。skills 目录隔离到 `tmp_path`，外部 HTTP/认证按规范处理。
- **不影响**：关键词匹配算法、SK2 的 frontmatter 解析、`match`/`load`/`list_skills` 契约、SK1/SK3 的注入语义、CLI 路径 `run_sync()`（行 408）每次扫描的现状（CLI 无长驻进程，不需要热加载；`run()` 不涉及 Skill 扫描/注入）。

## Dependencies

- **依赖 SK2（`skill-yaml-frontmatter`）**：重扫复用 SK2 的解析与结构化索引构建；构建逻辑抽取需基于 SK2 后的 `scan` 实现。
