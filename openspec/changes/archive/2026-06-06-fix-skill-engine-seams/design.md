## Context

`skill_admin_api.py` 通过两个 module-level callable seam 与 skill 引擎通信，便于测试隔离。当前两个 seam 是文档化的 placeholder，实现均不正确：

- `engine_reload()`：调用 `skill_registry.scan()`，后者执行 `_index.clear(); _index.update(new)`——两步操作之间 `_index` 为空，并发请求会看到空索引。正确实现是 `skill_registry.reload()`，后者先在局部变量构建新索引再原子 `global _index; _index = new_index` 替换。
- `engine_audit(content)`：直接返回 `{"verdict": "pass", "rules": []}`，完全绕过 `fleetent.skills.audit.audit()`，上传/编辑的 skill 内容从不经过安全检测。

两处均是单行修复，不需要接口变更或新依赖。

## Goals / Non-Goals

**Goals:**
- `engine_reload()` 调用原子 `reload()`，符合 `skill-hot-reload` spec 的原子切换要求
- `engine_audit(content)` 调用真实 `skill_audit.audit(content)`，符合 `skill-injection-audit` spec 的上传审计要求

**Non-Goals:**
- 不改变 seam 的对外签名（其他代码引用不受影响）
- 不修改 `skill_registry.reload()` 或 `skill_audit.audit()` 本身的实现

## Decisions

### D1：直接替换 seam 实现，不新增中间层

两个 seam 的存在目的本身就是"桥接 admin API 与 engine 实现"。正确做法是把 placeholder 替换为真实调用，而非再引入一层抽象。

### D2：`engine_audit` 使用 `skill_audit.audit(content)` 直接返回 dict

`audit.audit()` 返回 `{"verdict": str, "rules": list}`，与 seam 签名完全匹配，直接调用。

## Risks / Trade-offs

**[Risk] 真实审计会拒绝现有 suspicious/severe skill**
→ 预期行为：正是修复的目的。现有通过 upload 路径进入的 skill 下次 edit 时会被重新审计。存量文件不受影响（scan 时已审计）。

**[Risk] `reload()` 比 `scan()` 慢（构建完成前旧索引仍在服务）**
→ 可接受：`reload()` 本来的设计意图就是这个 trade-off，spec 明确要求原子性优先于速度。
