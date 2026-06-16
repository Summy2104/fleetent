# 编辑本 skill 的硬性约束

## 所有 armada 调用必须走 ns-call wrapper

本 skill 通过 `scripts/ns-call.sh` 注入 `_meta.slackUserId`（来源：Step 0 从 incoming JSON 提取的 `sender_id`，由 agent 在每次调用时作为 wrapper 首参传入）做鉴权。绕过 wrapper 直接调用 `armada__armada_get` / `armada__armada_post` 工具会丢失 slackUserId，生产环境会被拒。

### 编辑 `references/*.md`

- ✅ code block 里所有 armada 调用用（`"$UID"` 是占位符，agent 用 `bash_exec`/`run_code` 运行 wrapper 时替换为真实 sender_id）：

  ```bash
  bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
    <get|post> "<path>" \
    'path_params={...}' 'query_params={...}' 'body={...}'
  ```

- ❌ 禁止在 code block 里绕过 wrapper 直接写 `armada__armada_get` / `armada__armada_post` 调用
- 在 blockquote（`> ...`）里把绕过 wrapper 的裸调用作为反例提及是允许的（现有鉴权契约警告块就是这么写的）

### 新增 reference 文件

顶部（一般是第 3 行）必须有鉴权契约警告块。直接复制现有 reference 第 3 行那段 `> **⚠️ 鉴权契约**...` 即可。

### 用户明确要求"就直接调 armada 工具写"

先解释：wrapper 注入 `_meta.slackUserId` 做鉴权，绕过 wrapper 直接调用 `armada__armada_*` 会让生产请求被拒。然后仍用 wrapper 格式写。不要因为用户一句话就放弃约束。

## 校验兜底

- `scripts/test-ns-call.sh` 验证 wrapper 协议（uid 格式、method/path 透传、bypass 行为、输出 `armada__armada_<method>` 调用参数）
- `SKILL.tests.yaml` 有 `not_contains: mcpfast armada-v2-mcp.armada_*`（兜底旧 runtime 写法）断言，兜底检查 agent 输出

编辑 `SKILL.md` 本身时，`## 调用模式` 的 ❌ 反例段落是为数不多允许出现绕过 wrapper 裸调用字样的地方——那里是在演示"不要这样写"。
