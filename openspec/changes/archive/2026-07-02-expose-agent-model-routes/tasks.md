## 1. 后端验证：新路由键端到端 round-trip（不改契约）

- [x] 1.1 写失败测试：`tests/integration/test_agent_console_api.py` 新增用例，`PATCH /admin/agents/{name}`
      带 `model_overrides.routes` 含 `vision` / `kb_extraction` / `rerank`（各引用已注册模型），
      再 `GET /admin/agents/{name}` 断言这些路由键在回读的 `model_overrides` 中 round-trip
- [x] 1.2 写失败测试：`tests/integration/test_agent_materialize_export.py` 断言 materialize 后
      `agent.yaml` 的 `models.routes` 含上述键，且 `rerank` 目标解析为 `http_rerank`、
      `vision`/`kb_extraction` 解析为 `openai_chat`
- [x] 1.3 跑最窄命令见红：`uv run pytest tests/integration/test_agent_console_api.py -x -q`
      与 `tests/integration/test_agent_materialize_export.py -x -q`
- [x] 1.4 若已绿（现有 passthrough 已支持）：确认测试确实覆盖新路由键（断言键存在与 protocol），
      否则先修测试使其真正验证目标行为；无需改生产代码即可转绿则记录「后端无需改动」
- [x] 1.5 Verify green：两个 integration 文件通过

## 2. 前端：ROUTE_BINDINGS 补齐 5 个路由

- [x] 2.1 写失败测试（RTL）：在 `frontend/src/features/agents/` 新增/扩展测试，渲染 OverviewTab
      并断言 `vision` / `kb_extraction` / `rerank` / `audio_transcription` / `audio_generation`
      的模型选择器 label 均出现（用 mock 的 models/detail 查询）
- [x] 2.2 跑最窄命令见红：`pnpm exec vitest run src/features/agents/configure.test.tsx`
      （或选定的测试文件；用 `pnpm`，勿用 `npx`）
- [x] 2.3 实现：在 `configure.tsx` 的 `ROUTE_BINDINGS` 追加 5 个条目——
      `vision`（`['openai_chat']`）、`kb_extraction`（`['openai_chat']`）、`rerank`（`['http_rerank']`）、
      `audio_transcription`（占位协议）、`audio_generation`（占位协议），沿用现有渲染循环，使测试转绿
- [x] 2.4 Verify green：`pnpm exec vitest run <该测试文件>`

## 3. 前端：i18n 标签与音频空态提示

- [x] 3.1 写失败测试：断言新增 i18n 键存在且中英双语齐全（可在同一 RTL 测试用 label 文案断言，
      或最小 messages 键存在断言）
- [x] 3.2 实现：`src/i18n/messages.ts` 英文段与中文段同步新增
      `agents.modelVision` / `agents.modelKbExtraction` / `agents.modelRerank` /
      `agents.modelAudioTranscription` / `agents.modelAudioGeneration` 及音频空态 hint 键
- [x] 3.3 音频路由空态：候选为空时 `SimpleSelect` 呈现空态，并在该路由下渲染 hint 文案
      「暂无支持该协议的模型」
- [x] 3.4 Verify green：相关前端测试通过

## 4. 收尾校验

- [x] 4.1 前端类型/lint：`pnpm exec tsc --noEmit` 与 `pnpm exec biome check`（或项目既定命令）本分支干净
- [x] 4.2 后端 change 收尾：`make test-pr` + `make test-integration-ci` 两者全绿（无新增失败）
- [x] 4.3 手动核对：控制台 Agent 配置页出现全部 9 个路由选择器，`rerank` 候选仅 `http_rerank` 模型，
      音频路由呈现空态 hint
