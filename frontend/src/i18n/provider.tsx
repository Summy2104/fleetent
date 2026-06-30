import { type ReactNode, useEffect } from 'react'
import { I18nextProvider, useTranslation } from 'react-i18next'

import i18n from '@/i18n/config'
import {
  DEFAULT_LOCALE,
  type Locale,
  LOCALE_LIST,
  type LocaleMeta,
  type MessageKey,
} from '@/i18n/messages'

/**
 * i18n 运行时 —— 兼容层，对外契约与历史自研版保持一致（`useT()` / `useI18n()` /
 * `I18nProvider`），内部由 react-i18next 承载。
 *
 * 语言探测与持久化交由 `config.ts` 的 LanguageDetector（localStorage key
 * `fleetent.admin.locale`，`zh-*` 归一到 `zh`，未命中回退 `en`）。`<html lang>`
 * 经 `languageChanged` 监听同步。缺失 key 不抛错、回退显示 key（见 `config.ts`）。
 */

export type TranslateVars = Record<string, string | number>
export type Translate = (key: MessageKey, vars?: TranslateVars) => string

/** 把 i18next 的语言码（可能是 `zh-CN`）折叠回受支持的 `Locale`。 */
function normalize(language: string): Locale {
  return language.toLowerCase().startsWith('zh') ? 'zh' : DEFAULT_LOCALE
}

type I18nContextValue = {
  locale: Locale
  setLocale: (locale: Locale) => void
  toggleLocale: () => void
  t: Translate
  locales: LocaleMeta[]
}

export function I18nProvider({ children }: { children: ReactNode }): JSX.Element {
  useEffect(() => {
    const sync = (language: string): void => {
      document.documentElement.lang = normalize(language)
    }
    sync(i18n.language)
    i18n.on('languageChanged', sync)
    return () => {
      i18n.off('languageChanged', sync)
    }
  }, [])

  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

export function useI18n(): I18nContextValue {
  const { t, i18n: instance } = useTranslation()
  const locale = normalize(instance.language)
  return {
    locale,
    setLocale: (next: Locale) => {
      void instance.changeLanguage(next)
    },
    toggleLocale: () => {
      void instance.changeLanguage(locale === 'en' ? 'zh' : 'en')
    },
    t: t as Translate,
    locales: LOCALE_LIST,
  }
}

/** 便捷钩子：只取翻译函数，覆盖绝大多数组件的使用场景。 */
export function useT(): Translate {
  return useI18n().t
}
