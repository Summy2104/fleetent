## 1. 后端验证：多 entry fallback + per-entry 参数 round-trip（不改契约）

- [x] 1.1 写失败测试：`tests/integration/test_agent_materialize_export.py` 断言 `default` 路由配
      2 个 entry（各引用已注册 openai_chat 模型，第二个带 `max_tokens` + `params.temperature`）
      经 materialize 展开为 2-target fallback 链，且 `resolve("default")` 后 entry 参数正确合并
      （第二 target 的 temperature/max_tokens 生效）
- [x] 1.2 跑最窄命令见红：`uv run pytest tests/integration/test_agent_materialize_export.py -x -q`
- [x] 1.3 若已绿（passthrough 已支持）：确认测试确实断言了链长度、顺序与参数合并；否则先修测试
- [x] 1.4 Verify green：该 integration 文件通过

## 2. 前端逻辑：`routeEntries` / `withRouteEntries`（纯函数）

- [x] 2.1 写失败测试：`frontend/src/features/agents/configure-logic.test.ts` 覆盖
      `routeEntries`（解析多 entry、`params.temperature`、`max_tokens`、旧 `provider_id` 风格回落、
      空 overrides → 空数组）与 `withRouteEntries`（多 entry round-trip、丢空 params、
      空链删 route key、保留兄弟 route 与 credential slot）
- [x] 2.2 跑最窄命令见红：`pnpm exec vitest run src/features/agents/configure-logic.test.ts`
- [x] 2.3 实现：在 `configure-logic.ts` 增 `routeEntries` / `withRouteEntries`（沿用
      `withRouteModel` 的 sibling 保护语义），使测试转绿
- [x] 2.4 Verify green：`pnpm exec vitest run src/features/agents/configure-logic.test.ts`

## 3. 前端组件：`RouteChainEditor`（渐进式披露）

- [x] 3.1 写失败测试：`configure.test.tsx` 渲染 `ModelsTab`——加 fallback + 设 temperature → Save
      断言 PATCH body 的 `routes.default` 为 2-entry 链且第二 entry 含 `params.temperature`；
      reorder 改变保存顺序；单模型 route 仍存 1-entry 链
- [x] 3.2 跑最窄命令见红：`pnpm exec vitest run src/features/agents/configure.test.tsx`
- [x] 3.3 实现：抽出 `RouteChainEditor`，`ModelsTab` state 从 `Record<string,string>` 改为
      `Record<string, Entry[]>`；主选择器 + `+ add fallback` + reorder/remove + `override params`
      折叠区（temperature/max_tokens）；同链去重候选；保留 protocol 过滤、audio 空态、viewer 只读；
      `onSave` 用 `withRouteEntries` 折叠 `model_overrides`
- [x] 3.4 Verify green：`pnpm exec vitest run src/features/agents/configure.test.tsx`

## 4. 回归与收尾

- [x] 4.1 更新 `page.test.tsx` 既有 model-binding 用例以适配链编辑器 DOM（单选 round-trip、
      provider-key override 仍绑主 entry），保持行为断言
- [x] 4.2 `pnpm exec vitest run src/features/agents/` 全绿
- [x] 4.3 前端类型/lint：`pnpm exec tsc --noEmit` 与 `pnpm exec biome check <改动文件>` 干净
- [x] 4.4 后端收尾：`make test-pr` + `make test-integration-ci`（无新增失败）
- [x] 4.5 手动核对：Models tab 每 route 可加/删/排 fallback，设 temperature/max_tokens，
      单模型 route 外观不变；viewer 只读摘要
