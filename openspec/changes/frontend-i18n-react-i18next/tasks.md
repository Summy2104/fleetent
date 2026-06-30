> TDD 硬门禁：每个实现 task 先写测试见红 → 实现见绿。最窄命令：`pnpm --dir frontend vitest run <file>`。**测试任务在对应实现任务之前**。合并由主会话串行做。
>
> 前置：进入 frontend 目录操作；改动只在 `frontend/src/i18n/` 与 `frontend/package.json`，出口 `index.ts` 签名不得变。

## 0. 准备

- [ ] 0.1 grep 排查词条中是否有字面 `{`（非占位符），确认 `{x}`→`{{x}}` 批量替换安全：`rg "\{[^}]*\{|\}\}" frontend/src/i18n/messages.ts`（应无误报）。
- [ ] 0.2 安装依赖：`pnpm --dir frontend add i18next react-i18next i18next-browser-languagedetector`。

## 1. 词条插值迁移（messages.ts）

- [ ] 1.1 脚本批量把 `messages.ts` 中占位符 `{name}` → `{{name}}`（132 词条 × 中英）；更新文件头注释从「`{name}` 形式」改为「`{{name}}` 形式」。`git diff` 目测 + 数量核对（替换前 `rg -c "\{\w+\}"` 与替换后 `rg -c "\{\{\w+\}\}"` 对齐）。
- [ ] 1.2 `messages.ts` 末尾 `export default en`（供 `i18n.d.ts` 取类型源）；`pnpm --dir frontend typecheck` 通过。

## 2. i18next 单例与类型（config.ts + i18n.d.ts）

- [ ] 2.1 新增 `config.ts`：`i18n.use(LanguageDetector).use(initReactI18next).init({...})`，含 `resources`(en/zh)、`fallbackLng:'en'`、`supportedLngs`、`load:'languageOnly'`、`keySeparator:false`、`nsSeparator:false`、`interpolation.escapeValue:false`、detection(order/lookupLocalStorage `fleetent.admin.locale`/caches)、`react.useSuspense:false`、DEV `missingKeyHandler`。
- [ ] 2.2 新增 `i18n.d.ts`：`declare module 'i18next'` 声明合并，`resources.translation = typeof en`、`keySeparator: false`。`pnpm --dir frontend typecheck` 通过（调用点补全生效）。

## 3. 兼容层（provider.tsx，TDD）

- [ ] 3.1 改写 `i18n.test.tsx` 覆盖新契约：`useT()('nav.agents')` 取值、`{{name}}` 插值、`toggleLocale`/`setLocale` 切换、缺失 key 回退返回 key、`<html lang>` 同步；`beforeEach` 复位 i18next（`changeLanguage('en')`）+ 清 localStorage。先跑见红。
- [ ] 3.2 重写 `provider.tsx` 为兼容层：`I18nProvider` 包 `I18nextProvider` + `languageChanged` 同步 `<html lang>`；`useI18n` 架在 `useTranslation` 复刻 `{locale,setLocale,toggleLocale,t,locales}`（含 `normalize` 折叠 `zh-*`→`zh`）；`useT` 不变。跑 3.1 见绿。

## 4. 清理与出口校验

- [ ] 4.1 删除 `provider.tsx` 旧死代码（`interpolate` / `detectLocale` / 基于 `CATALOGS` 的手写 `t`、`STORAGE_KEY` 等已被取代者）；确认 `index.ts` 出口符号集合**未变**。
- [ ] 4.2 `pnpm --dir frontend lint` 无未用导出/变量告警。

## 5. Change 收尾验证

- [ ] 5.1 `pnpm --dir frontend vitest run src/i18n/i18n.test.tsx` 全绿。
- [ ] 5.2 `make test-frontend`（vitest + coverage + tsc --noEmit + biome）全绿；特意构造一处 `t('不存在key')` 验证 tsc 报错后回退删除。
- [ ] 5.3 `pnpm --dir frontend build` 成功。
- [ ] 5.4 人工冒烟：启动 dev，切换中英、刷新保持、`<html lang>` 跟随、句中插值正确显示。
