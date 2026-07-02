import i18n from 'i18next'
import LanguageDetector from 'i18next-browser-languagedetector'
import { initReactI18next } from 'react-i18next'

import { CATALOGS, DEFAULT_LOCALE } from '@/i18n/messages'

/**
 * i18next 单例 —— 词条以内联 `resources` 同步加载（体量小，无需 http-backend 懒加载）。
 *
 * 关键约束：
 * - `keySeparator: false` —— 词条用扁平点分 key（如 `nav.agents`），不可被当作嵌套解析。
 * - 插值用 i18next 原生 `{{name}}`；`escapeValue: false` 因 React 已防 XSS。
 * - 语言探测优先 localStorage（key 沿用 `fleetent.admin.locale`），其次浏览器语言；
 *   `load: 'languageOnly'` 把 `zh-CN`/`zh-TW` 归一到 `zh`，未命中回退 `en`。
 * - 缺失 key 不抛错（i18next 默认回退返回 key 本身）；开发期 `console.warn` 提示。
 */

const STORAGE_KEY = 'fleetent.admin.locale'

void i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      en: { translation: CATALOGS.en },
      zh: { translation: CATALOGS.zh },
    },
    fallbackLng: DEFAULT_LOCALE,
    supportedLngs: ['en', 'zh'],
    load: 'languageOnly',
    keySeparator: false,
    nsSeparator: false,
    interpolation: { escapeValue: false },
    detection: {
      order: ['localStorage', 'navigator'],
      lookupLocalStorage: STORAGE_KEY,
      caches: ['localStorage'],
    },
    react: { useSuspense: false },
    saveMissing: import.meta.env.DEV,
    missingKeyHandler: (_lngs, _ns, key) => {
      if (import.meta.env.DEV) {
        console.warn(`[i18n] missing message key: ${key}`)
      }
    },
  })

export default i18n
