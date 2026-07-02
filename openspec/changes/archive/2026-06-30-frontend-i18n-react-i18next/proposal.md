## Why

前端 admin SPA 的 i18n 当前是一套**自研实现**（`frontend/src/i18n/`）：扁平点分 key 词条目录（`en`/`zh` 两份 TS 对象，约 1164 词条）、Context provider 暴露 `useT()` / `useI18n()`、`{name}` 单括号插值、localStorage 持久化 + 浏览器语言探测。它够用，但缺少成熟库才有的能力，且需团队自行维护：

- **句中带交互标签的文案**只能拆 key 拼接或塞 HTML 字符串，语序一变就崩，无干净方案。
- 复数规则、日期/数字本地化等需自行实现。
- 插值、回退、探测、持久化逻辑全是手写代码，需自行测试与维护。

迁移到生态事实标准 **react-i18next**，可在**不改动 1164 个调用点**的前提下接入成熟库能力，并保留现有的两项关键保障：**编译期「漏翻报错」**与**缺失 key 不抛错回退**。

## What Changes

采用**兼容层**方案——`frontend/src/i18n/index.ts` 对外导出签名（`useT` / `useI18n` / `I18nProvider` / `LOCALES` / 类型等）完全不变，故所有消费方文件零改动：

- **新增依赖**：`i18next`、`react-i18next`、`i18next-browser-languagedetector`。
- **词条**：`messages.ts` 仍是 `en`/`zh` 两份 TS 对象（`en` 为权威源、`zh: Messages` 强制对齐），作为 `resources` 喂给 i18next。插值占位符由 `{name}` 批量改为 i18next 原生的 `{{name}}`（132 词条 × 中英，机械替换；调用点 `t('key', { name })` 不变）。
- **新增 `config.ts`**：创建并 `init` i18next 单例——`resources` 内联、`LanguageDetector`、`keySeparator: false`（key 含字面点，禁用嵌套解析）、`{{}}` 插值、`escapeValue: false`、缺失 key 在 DEV `console.warn`。
- **新增 `i18n.d.ts`**：`i18next` 声明合并，以 `en` 为类型源 → 保留调用点 key 自动补全与「不存在 key 编译期报错」。
- **重写 `provider.tsx` 为兼容层**：`I18nProvider` 内包 `I18nextProvider`；`useI18n` 架在 `useTranslation` 之上复刻 `{ locale, setLocale, toggleLocale, t, locales }` 契约；`document.documentElement.lang` 经 `languageChanged` 监听同步；localStorage 持久化交由 detector 的 `caches`。
- **语言探测/持久化**：`i18next-browser-languagedetector` 配成与现有行为一致（优先 localStorage、key `fleetent.admin.locale` 不变、`zh-*` 归一到 `zh`、其余回退 `en`）。
- **测试**：适配 `i18n.test.tsx`；i18next 单例在测试间复位避免顺序依赖。
- **清理**：删除旧 `interpolate` / `detectLocale` / 基于 `CATALOGS` 的手写 `t` 死代码。

## Capabilities

### New Capabilities
- `admin-frontend-i18n`：admin SPA 的多语言能力（中英双语、运行时切换、localStorage 持久化、浏览器语言探测、编译期类型安全与缺失 key 安全回退），由 react-i18next 承载，对外经 `useT` / `useI18n` 公开。

## Impact

- **新增**：
  - `frontend/src/i18n/config.ts`（i18next 单例 init）
  - `frontend/src/i18n/i18n.d.ts`（声明合并）
  - `frontend/package.json` 三个依赖
- **改动**：
  - `frontend/src/i18n/provider.tsx`（重写为兼容层）
  - `frontend/src/i18n/messages.ts`（`{x}`→`{{x}}`；`export default en` 供 d.ts 取类型；更新文件头注释）
  - `frontend/src/i18n/i18n.test.tsx`（适配新实现）
- **不改动**：`frontend/src/i18n/index.ts` 出口签名不变 → `useT`/`useI18n`/`LanguageSwitcher` 等所有消费方文件零改动。
- **边界声明**：
  - owning package：`frontend`（admin SPA 的 `src/i18n/` 子域）
  - public API surface：`src/i18n/index.ts` 导出**不变**（`useT` / `useI18n` / `I18nProvider` / `LOCALES` / `LOCALE_LIST` / `DEFAULT_LOCALE` / 类型 `Locale` / `LocaleMeta` / `MessageKey` / `Messages` / `Translate` / `TranslateVars`）
  - owned tables：无
  - config namespace：无（沿用既有 localStorage key `fleetent.admin.locale`）
  - cross-module dependencies：新增前端 npm 依赖 `i18next` / `react-i18next` / `i18next-browser-languagedetector`；不触碰后端、不触碰 agent 运行时
  - migration / shim plan：兼容层即 shim——`provider.tsx` 重写但出口契约不变，调用点无需迁移；后续如需可渐进改用原生 `useTranslation`（非本变更目标）
- **不碰**：后端任何模块、agent 运行时、其他前端 feature 域。纯前端 i18n 子域改造。
