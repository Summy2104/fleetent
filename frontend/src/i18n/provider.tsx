import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

import {
  CATALOGS,
  DEFAULT_LOCALE,
  LOCALES,
  LOCALE_LIST,
  type Locale,
  type LocaleMeta,
  type MessageKey,
} from '@/i18n/messages';

/**
 * i18n 运行时 —— 与 `app/theme.tsx` 同构的 context 方案：localStorage 持久化用户选择，
 * 首次访问无存储时按浏览器语言探测（`zh-*` → 中文，其余 → 英文）。
 *
 * 暴露 `useT()` 取翻译函数 `t(key, vars?)`，`{name}` 形式占位符按 `vars` 插值；
 * 缺失 key 在开发期 `console.warn` 并回退显示 key 本身，绝不抛错中断渲染。
 */

const STORAGE_KEY = 'fleetent.admin.locale';

export type TranslateVars = Record<string, string | number>;
export type Translate = (key: MessageKey, vars?: TranslateVars) => string;

function detectLocale(): Locale {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY) as Locale | null;
    if (stored && stored in LOCALES) {
      return stored;
    }
  } catch {
    /* localStorage 不可用（隐私模式等），退回探测 */
  }
  try {
    if (window.navigator.language.toLowerCase().startsWith('zh')) {
      return 'zh';
    }
  } catch {
    /* 无 navigator（SSR/测试）时退回默认 */
  }
  return DEFAULT_LOCALE;
}

function interpolate(template: string, vars?: TranslateVars): string {
  if (!vars) {
    return template;
  }
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in vars ? String(vars[name]) : match
  );
}

type I18nContextValue = {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  toggleLocale: () => void;
  t: Translate;
  locales: LocaleMeta[];
};

const I18nContext = createContext<I18nContextValue | null>(null);

export function I18nProvider({ children }: { children: ReactNode }): JSX.Element {
  const [locale, setLocaleState] = useState<Locale>(() => detectLocale());

  useEffect(() => {
    document.documentElement.lang = locale;
    try {
      window.localStorage.setItem(STORAGE_KEY, locale);
    } catch {
      /* 持久化失败可忽略 */
    }
  }, [locale]);

  const t = useCallback<Translate>(
    (key, vars) => {
      const catalog = CATALOGS[locale] ?? CATALOGS[DEFAULT_LOCALE];
      const template = catalog[key] ?? CATALOGS[DEFAULT_LOCALE][key];
      if (template === undefined) {
        if (import.meta.env?.DEV) {
          console.warn(`[i18n] missing message key: ${key}`);
        }
        return key;
      }
      return interpolate(template, vars);
    },
    [locale]
  );

  const value = useMemo<I18nContextValue>(
    () => ({
      locale,
      setLocale: setLocaleState,
      toggleLocale: () => setLocaleState((current) => (current === 'en' ? 'zh' : 'en')),
      t,
      locales: LOCALE_LIST,
    }),
    [locale, t]
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const context = useContext(I18nContext);
  if (!context) {
    throw new Error('useI18n must be used within an I18nProvider');
  }
  return context;
}

/** 便捷钩子：只取翻译函数，覆盖绝大多数组件的使用场景。 */
export function useT(): Translate {
  return useI18n().t;
}
