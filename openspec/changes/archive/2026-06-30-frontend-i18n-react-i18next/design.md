# 设计：前端 i18n 迁移至 react-i18next（兼容层）

## 目标与非目标

**目标**

- 用 react-i18next 替换自研 i18n 运行时，**不改动任何调用点**（1164 处 `t('key')`）。
- 保留两项关键保障：调用点「不存在 key 编译期报错」+ zh 漏翻 en 的 key「编译期报错」；缺失 key 运行时不抛错、回退显示 key。
- 复刻现有探测/持久化行为（localStorage key `fleetent.admin.locale`、`zh-*`→`zh`、回退 `en`）。

**非目标（YAGNI）**

- 不引入 http-backend 懒加载（1164 词条体量小，单包内联即可）。
- 不新增语言、不接入 ICU / 复数（保留扩展可能，本次不做）。
- 不把调用点改为原生 `useTranslation`（兼容层保持现有手感；如未来需要可渐进迁移）。

## 关键决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 调用点策略 | **兼容层**保留 `useT`/`t('key')` | 1164 调用点零改动，风险最低 |
| 词条格式 | **保留 TS 对象**作 `resources` | 保住编译期类型安全；`messages.ts` 主体不动 |
| 插值语法 | **`{name}`→`{{name}}`** | 用 i18next 原生默认语法，更地道；机械可脚本化 |
| 探测/持久化 | **i18next-browser-languagedetector** | 地道、自动写回 localStorage，配置复刻现有行为 |

## 架构

```
src/i18n/
  messages.ts   en/zh 词条（权威源 + Messages 对齐）；export default en 供类型源
  config.ts     创建 i18next 单例并 init（resources/detector/插值/keySeparator）
  i18n.d.ts     declare module 'i18next' 声明合并（resources.translation = typeof en）
  provider.tsx  兼容层：I18nProvider(包 I18nextProvider) + useI18n/useT 复刻契约
  index.ts      出口不变（再导出 provider 与 messages 的公开符号）
```

数据流：`I18nProvider` 挂载 i18next 单例 → 组件 `useT()`/`useI18n()` → 内部 `useTranslation()` → i18next 按当前 `language` 从 `resources` 取词条并插值。语言切换经 `i18n.changeLanguage`，detector `caches:['localStorage']` 自动持久化，`languageChanged` 监听同步 `<html lang>`。

## config.ts 要点

```ts
i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: { en: { translation: en }, zh: { translation: zh } },
    fallbackLng: 'en',
    supportedLngs: ['en', 'zh'],
    load: 'languageOnly',          // zh-CN/zh-TW → zh
    keySeparator: false,           // ⚠️ key 含字面点（nav.agents），禁用嵌套解析
    nsSeparator: false,
    interpolation: { escapeValue: false },   // React 自带防 XSS
    detection: {
      order: ['localStorage', 'navigator'],
      lookupLocalStorage: 'fleetent.admin.locale',
      caches: ['localStorage'],
    },
    react: { useSuspense: false }, // resources 同步内联，无需 Suspense
    saveMissing: import.meta.env.DEV,
    missingKeyHandler: (_lng, _ns, key) => {
      if (import.meta.env.DEV) console.warn(`[i18n] missing message key: ${key}`)
    },
  })
```

**`keySeparator: false` 是本方案最易踩的坑**：key 是扁平含点的 `nav.agents`，不禁用会被当成 `nav→agents` 嵌套，查不到全部失效（冒烟立刻暴露）。

## 兼容层（provider.tsx）

```tsx
export function I18nProvider({ children }: { children: ReactNode }): JSX.Element {
  useEffect(() => {
    const sync = (lng: string) => { document.documentElement.lang = normalize(lng) }
    sync(i18n.language)
    i18n.on('languageChanged', sync)
    return () => i18n.off('languageChanged', sync)
  }, [])
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

export function useI18n(): I18nContextValue {
  const { t, i18n } = useTranslation()
  const locale = normalize(i18n.language)
  return {
    locale,
    setLocale: (l: Locale) => void i18n.changeLanguage(l),
    toggleLocale: () => void i18n.changeLanguage(locale === 'en' ? 'zh' : 'en'),
    t: t as Translate,
    locales: LOCALE_LIST,
  }
}
export function useT(): Translate { return useI18n().t }
```

`normalize(lng)`：把 `zh-CN` 等折叠回 `'en'|'zh'`（detector 已 `load: languageOnly`，此处兜底）。

## 类型安全（双层，均保留）

| 层 | 机制 | 作用 |
|---|---|---|
| 调用点 | `i18n.d.ts` 声明合并，`resources.translation = typeof en` | `t('不存在key')` 编译期报错 + 自动补全 |
| zh 对齐 | `messages.ts` 中 `zh: Messages`（原样保留） | zh 漏一个 en 的 key 编译期报错 |

## 错误处理

- 缺失 key：i18next 默认回退返回 key 本身（与原 `t` 行为一致）；DEV 下 `missingKeyHandler` `console.warn`。
- detector / localStorage 不可用：detector 内部静默回退；`fallbackLng: 'en'` 兜底。
- 不吞异常以外的错误：init 是同步内联，失败即构建期暴露。

## 测试策略

- 层级：前端单测（Vitest + Testing Library），`frontend/src/i18n/i18n.test.tsx`。
- 用例：`useT()('nav.agents')` 取值、`toggleLocale`/`setLocale` 切换、`{{name}}` 插值、缺失 key 回退、`<html lang>` 同步。
- 隔离：i18next 单例跨测试需复位（`beforeEach` `i18n.changeLanguage('en')` + 清 localStorage），避免顺序依赖。
- 命令：`pnpm --dir frontend vitest run src/i18n/i18n.test.tsx`（红/绿）；收尾 `make test-frontend`（vitest+coverage+tsc+biome）。

## 风险与回滚

- **风险**：`keySeparator: false` 漏配 → 翻译全失效（冒烟暴露）；词条含字面 `{` 致插值脚本误改 → 步骤前先 grep 排查。
- **回滚**：分步独立 commit，出口契约不变，`git revert` 可整体回退，不留半迁移态。
