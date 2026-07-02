> TDD 硬门禁：每个实现 task 先写测试见红 → 再实现见绿。最窄命令：后端 `uv run pytest <file>::<test> -x -q`，前端 `pnpm --dir frontend exec vitest run <file>`。测试任务在对应实现任务之前。

## 1. store 层：`update_source`（integration，真实 DB）

- [ ] 1.1 在 `tests/integration/test_webhook_source_store.py` 写测试并见红：
  - `update_source` 更新常规字段（user_id/agent_id/message_template/reply_target/enabled）后 `get_source` 反映新值；
  - `secret_action="keep"` 时已有密钥保持不变；
  - `secret_action="set"` 时密钥被新值覆盖（`get_source().secret` == 新值，且库内为密文）；
  - `secret_action="clear"` 时密钥变 None；
  - `update_source` 对不存在的 id 不新建行（区别于 upsert 的 `put_source`）。
- [ ] 1.2 实现 `webhook_source_store.update_source(*, id, user_id, agent_id, message_template, reply_target, enabled, secret_action, secret=None)`：`UPDATE`（非 upsert），`keep` 不进 SET 子句、`set`/`clear` 才写 `secret_ciphertext`，刷新 `updated_at`。跑 1.1 见绿。

## 2. admin API：`PUT /admin/webhooks/sources/{id}`（integration，FastAPI + 真实 DB）

- [ ] 2.1 在 `tests/integration/test_webhook_admin_api.py` 写测试并见红：
  - PUT 更新常规字段成功、响应是 `_public_view`（无明文 secret、含 `has_secret`）；
  - `secret_action` 三态：`keep` 保持、`set` 更换（`set` 缺 `secret` → 400）、`clear` 清空后 `has_secret=false`；
  - 不存在的 id → 404；
  - 非管理员会话 → 401/403；
  - 写入 `webhook.update` 审计。
- [ ] 2.2 实现：`WebhookSourceUpdateBody`（含 `secret_action: Literal["keep","set","clear"]`，默认 `keep`）+ `PUT` 端点（先 `get_source` 判 404 → `set` 校验 secret → `update_source` → 审计 → 返回 `_public_view`）。跑 2.1 见绿。

## 3. 前端数据层（api.ts，Vitest + MSW）

- [ ] 3.1 在 `frontend/src/features/webhooks/api.test.tsx` 写测试并见红：`useUpdateWebhookSourceMutation(id)` 调 `PUT /admin/webhooks/sources/{id}`，mutation 后失效列表查询；请求体含 `secret_action`。
- [ ] 3.2 实现 `WebhookSourceUpdateInput` 类型 + `useUpdateWebhookSourceMutation`。跑 3.1 见绿。

## 4. 前端弹窗（page.tsx，Vitest + MSW）

- [ ] 4.1 在 `frontend/src/features/webhooks/page.test.tsx` 写测试并见红：
  - 行操作菜单有「查看/编辑」入口，打开弹窗默认只读展示全部字段（含 message_template、reply_target 名称、密钥「已设置/未设置」）；
  - 点「编辑」进入可改态，`id` 只读；
  - 保存触发 `PUT`，请求体 `secret_action` 默认 `keep`；点「更换密钥」填值后 body 为 `set` + secret；点「清除密钥」后 body 为 `clear`；
  - 保存成功后回只读态、列表刷新。
- [ ] 4.2 实现查看/编辑弹窗（复用新建弹窗控件，只读↔编辑切换、密钥三态动作）。跑 4.1 见绿。

## 5. i18n

- [ ] 5.1 `frontend/src/i18n/messages.ts` 补 `webhooks.*` 新词条（查看/编辑/保存/取消/更换密钥/清除密钥/密钥已设置/未设置等）的 en + zh（en 权威源，zh 类型强制对齐，两边都写）。

## 6. Change 收尾验证

- [ ] 6.1 后端：`uv run pytest tests/integration/test_webhook_admin_api.py tests/integration/test_webhook_source_store.py -q` 全绿；`make test-pr` 无新增失败。
- [ ] 6.2 前端：`make test-frontend` 全绿（vitest + 覆盖率 + tsc --noEmit + lint）。
- [ ] 6.3 手动核对：`/admin/ui` webhooks 页可打开某条查看到全部字段、编辑常规字段生效、密钥「保持/更换/清除」行为正确、`id` 不可改。
