# MCP wrapper 已知问题与能力面

> **⚠️ 鉴权契约**：本文档所有示例中的 `"$UID"` 是占位符，agent 在实际用 bash_exec/run_code 运行 wrapper 时须替换为 Step 0 从 incoming JSON 提取的 `sender_id`。`_meta={"slackUserId":"..."}` 由 wrapper 内部自动注入。**严禁绕过 wrapper 直接调用 `armada__armada_get` / `armada__armada_post` 工具**。规则见 `SKILL.md §调用模式`。

本文档集中登记 `armada` MCP server（工具 `armada__armada_get` / `armada__armada_post`）及其 wrapper (`scripts/ns-call.sh`) 的**已知问题**与**能力限制**。调用写端点、遇到字段"看起来传了但没生效"的场景，先来这里查。

## 1. Wrapper 能力面

| method | 支持 | 说明 |
|--------|------|------|
| `get` | ✅ | 现可用 |
| `post` | ✅ | 现可用 |
| `put` | ❌ | 未实现 |
| `patch` | ❌ | 未实现 |
| `delete` | ❌ | 未实现 |

**根因**：`ns-call.sh` 的 method 校验只接受 `<get\|post>`：
```bash
METHOD="${2:?usage: ns-call.sh <uid> <get|post> <path> [kv...]}"
```

**影响**：`docs/bs-contracts/ns-write-endpoints.md` 契约 §5（`PATCH /v1/payments/{id}/txid`）当前无法走 wrapper 落地。

**后续路径**（独立 PR）：扩展 wrapper 支持 `put|patch|delete`，然后按契约落 7 个 MVP 写端点到 `common-ns-masterdata` / `common-ns-process` 子 skill。

## 2. 已知字段丢失（POST 静默丢）

### #1 `POST /v1/projects` 丢弃 `owner_ids`

| 项 | 值 |
|----|-----|
| 端点 | `POST /v1/projects` |
| 字段 | `owner_ids` |
| 症状 | wrapper 转发给 armada 工具时 **静默丢失**；body 传入有值但 NS 后端存储为 `[]` |
| 发现时间 | 2026-04-21 |
| 发现者 | `bs-project-drafting` |
| 规避 | 短期由 BS 在 NS 页面手工补填；待 RD 修 wrapper |
| 修复状态 | 未修（pending） |

### #2 `POST /v1/projects` 丢弃 `contains_bm_funds`

| 项 | 值 |
|----|-----|
| 端点 | `POST /v1/projects` |
| 字段 | `contains_bm_funds` |
| 症状 | wrapper 转发给 armada 工具时静默丢失；body 传 `1` 或 `2` 均存为 `0` |
| 发现时间 | 2026-04-21 |
| 发现者 | `bs-project-drafting` |
| 规避 | BS 在 NS 页面手工修改，或用 PUT 方式回填（等 PUT 支持） |
| 修复状态 | 未修（pending） |

## 3. 新增已知问题时的登记格式

```markdown
### #N {端点} 丢弃 {字段} / {症状简述}

| 项 | 值 |
|----|-----|
| 端点 | HTTP method + path |
| 字段 | 受影响字段名 |
| 症状 | 精确描述（"传 X 存为 Y"，"返回 Z"）|
| 发现时间 | YYYY-MM-DD |
| 发现者 | 哪个 skill / 哪个 agent |
| 规避 | 短期怎么办 |
| 修复状态 | 未修 / 已排期 / 已修（commit SHA） |
```

## 4. 紧急降级开关

```
NS_CALL_BYPASS=1
```

设置为环境变量后，wrapper 跳过全部鉴权 + `_meta` 注入，直接输出裸 `armada__armada_<method>` 调用参数。**仅供运维调试/应急使用**，开启时 wrapper 会在 stderr 输出警告。

此开关**不应在生产环境启用**；也不是日常规避已知 bug 的方法。

## 5. 汇报流程

发现新 wrapper bug 时：
1. 立即登记到本文档（按 §3 格式）
2. 在下游 skill（如 `bs-*-drafting/references/*.md`）引用本条目作为规避依据
3. 同步开 RD 修复 Jira（负责人：wrapper 维护团队）
4. 修复后回填"修复状态"字段和 commit SHA，并在下游 skill 移除临时规避
