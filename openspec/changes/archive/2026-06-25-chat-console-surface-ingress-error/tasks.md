## 1. 透出 ingress 错误 detail

- [x] 1.1 测试(vitest):503 响应体 `{detail: "node 'local-node' service key unavailable"}` → 控制台显示该 detail,不再显示 "no active placement"(红)
- [x] 1.2 实现:`api.ts` 错误分支读取 `await response.json()`(try/catch 容错),提取 `detail`;`toIngressError` 改为基于 detail 呈现(有 detail 透出,带 agent 名前缀)
- [x] 1.3 测试通过(绿)

## 2. 无 detail 的中性回落

- [x] 2.1 测试:503 空体/非 JSON → 显示中性 "unavailable" 文案,且**不**含 "no node placement"/"no active placement" 断言;404 空体 → "not found"(红)
- [x] 2.2 实现:`detail` 缺失/解析失败时按状态码回落(404→not found,503→neutral unavailable,其他→generic failed),去掉 placement 硬编码
- [x] 2.3 测试通过(绿)

## 3. 更新既有用例对齐后端契约

- [x] 3.1 修 `api.test.tsx` 既有 "maps 404 and 503 ingress errors" 用例:mock body 从 `{error: ...}` 改为 FastAPI 真实形状 `{detail: ...}`,断言透出 detail(不再断言旧 placement 文案)
- [x] 3.2 确认 404 用例同样基于 detail / 中性回落,语义清晰

## 4. 前端门禁

- [x] 4.1 运行 `make test-frontend`(vitest run --coverage + tsc --noEmit + eslint)全绿
- [x] 4.2 确认无新增 TypeScript / eslint 报错(本 change 触碰的 `features/chat`)
