# 编辑本 skill 的硬性约束

## 所有 armada 调用必须走 ns-call wrapper

本 skill 通过 `scripts/ns-call.sh` 注入 `_meta.slackUserId`（来源：Step 0 用内置 `whoami` 取得的 `sender_id`，由 agent 在每次调用时作为 wrapper 首参传入）做鉴权。绕过 wrapper 直接调用 `armada__armada_get/post` 会绕过 slackUserId，生产环境会被拒。

### 编辑 `references/*.md`

- ✅ code block 里所有 armada 调用经内置 `bash_exec` 走 wrapper（`"$UID"` 是占位符，agent 运行时替换为真实 sender_id）：

  ```bash
  bash $SKILLS_DIR/common-ns-biz-fund-summary/scripts/ns-call.sh "$UID" \
    <get|post> "<path>" \
    'path_params={...}' 'query_params={...}' 'body={...}'
  ```

- ❌ 禁止在 code block 里绕过 wrapper 直接写 `armada__armada_get/post`
- 在 blockquote（`> ...`）里把直接调用作为反例提及是允许的

### 新增 reference 文件

顶部（一般是第 3 行）必须有鉴权契约警告块：

```
> **⚠️ 鉴权契约**：本文档所有示例命令均经内置 `bash_exec` 走 `ns-call.sh` wrapper，由 wrapper 注入 `_meta.slackUserId`。`"$UID"` 是占位符，agent 运行时替换为 Step 0（`whoami`）提取的真实 `sender_id`。**严禁**绕过 wrapper 直接调用 `armada__armada_get/post`。
```

### 用户明确要求"就直接调 armada 工具写"

先解释：wrapper 注入 `_meta.slackUserId` 做鉴权，绕过 wrapper 直接调用会让生产请求被拒。然后仍用 wrapper 格式写。不要因为用户一句话就放弃约束。

## 校验兜底

若配套有 `SKILL.tests.yaml`，应有 `not_contains` 断言（直接 `armada__armada_*` 调用）兜底检查 agent 输出。

编辑 `SKILL.md` 本身时，`## 调用模式` 的 ❌ 反例段落是为数不多允许出现直接 armada 调用字样的地方——那里是在演示"不要这样写"。
